"""Command line: generate a dataset, validate it, audit the validator, evaluate a model, report."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from .adapters import (
    ReplayAdapter,
    Adapter, GeminiAdapter, OpenAICompatibleAdapter, OracleAdapter, RandomAdapter, ThrottledAdapter,
)
from .evaluate import evaluate
from .mutate import audit
from .report import write_report
from .tasks import build_dataset, load_tasks, make_map
from .render import build_primitives, to_svg


def _adapter(args: argparse.Namespace, data_dir: Path) -> Adapter:
    if args.adapter == "oracle":
        return OracleAdapter(data_dir)
    if args.adapter == "random":
        return RandomAdapter(args.seed)
    if args.adapter == "gemini":
        return GeminiAdapter(args.model or "gemini-2.5-flash")
    if args.adapter == "replay":
        if not args.answers:
            raise SystemExit("--adapter replay needs --answers")
        return ReplayAdapter(Path(args.answers), args.name)
    if args.adapter == "openai":
        if not (args.base_url and args.model):
            raise SystemExit("--adapter openai needs --base-url and --model")
        return OpenAICompatibleAdapter(args.base_url, args.model)
    raise SystemExit(f"unknown adapter {args.adapter}")


def cmd_generate(args: argparse.Namespace) -> int:
    manifest = build_dataset(Path(args.out), args.maps, args.questions, args.seed, args.tier)
    print(json.dumps(manifest, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from .parse_svg import parse_svg
    from .questions import answer_for

    data_dir = Path(args.data)
    tasks = load_tasks(data_dir)
    failures = 0
    for task in tasks:
        parsed = parse_svg((data_dir / str(task["svg"])).read_text(encoding="utf-8"))
        derived = answer_for(str(task["kind"]), dict(task["params"]), parsed.network)  # type: ignore[arg-type]
        if parsed.issues or derived != task["answer"]:
            failures += 1
            print(f"FAIL {task['task_id']}: {parsed.issues or derived!r}")
    print(f"{len(tasks) - failures}/{len(tasks)} tasks re-derived from the drawing alone")
    return 1 if failures else 0


def cmd_audit(args: argparse.Namespace) -> int:
    totals: dict[str, list[int]] = {}
    for index in range(args.maps):
        m, _ = make_map(args.seed, index)
        svg = to_svg(m, build_primitives(m))
        for name, (caught, applied) in audit(m, svg, random.Random(args.seed + index)).items():
            slot = totals.setdefault(name, [0, 0])
            slot[0] += caught
            slot[1] += applied
    print("| Corruption | Caught / applied |\n|---|---|")
    for name, (caught, applied) in totals.items():
        print(f"| {name} | {caught}/{applied} |")
    return 0 if all(c == a for c, a in totals.values()) else 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    tasks = load_tasks(data_dir)
    if args.limit:
        tasks = tasks[: args.limit]
    adapter = _adapter(args, data_dir)
    if args.delay > 0:
        adapter = ThrottledAdapter(adapter, args.delay)
    rows = evaluate(adapter, data_dir, tasks, data_dir / "results.jsonl", args.workers)
    correct = sum(1 for r in rows if r["correct"])
    print(f"{adapter.name}: {correct}/{len(rows)} correct")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    text = write_report(data_dir, data_dir / "results.jsonl", data_dir / "report.md", load_tasks(data_dir))
    print(text)
    return 0


def cmd_degrade(args: argparse.Namespace) -> int:
    """Copy a dataset with degraded images (downscale plus JPEG artefacts) to test robustness."""
    import io
    import json
    import shutil

    from PIL import Image

    src, dst = Path(args.data), Path(args.out)
    (dst / "images").mkdir(parents=True, exist_ok=True)
    for name in ("tasks.jsonl",):
        shutil.copy(src / name, dst / name)
    if (src / "maps").exists():
        shutil.copytree(src / "maps", dst / "maps", dirs_exist_ok=True)
    count = 0
    for path in sorted((src / "images").glob("*.png")):
        with Image.open(path) as image:
            image = image.convert("RGB")
            size = (max(1, round(image.width * args.scale)), max(1, round(image.height * args.scale)))
            small = image.resize(size, Image.LANCZOS)
        buffer = io.BytesIO()
        small.save(buffer, "JPEG", quality=args.quality)
        buffer.seek(0)
        Image.open(buffer).convert("RGB").save(dst / "images" / path.name, optimize=True)
        count += 1
    manifest = json.loads((src / "manifest.json").read_text()) if (src / "manifest.json").exists() else {}
    manifest["degraded"] = {"scale": args.scale, "jpeg_quality": args.quality}
    (dst / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"degraded {count} images (scale {args.scale}, jpeg quality {args.quality}) -> {dst}")
    return 0


def cmd_gallery(args: argparse.Namespace) -> int:
    """Write a markdown gallery of wrong answers: image, question, model reply, reference."""
    import json
    import shutil

    data, out = Path(args.data), Path(args.out)
    tasks = {t["task_id"]: t for t in (json.loads(l) for l in (data / "tasks.jsonl").read_text().splitlines() if l.strip())}
    rows = [json.loads(l) for l in (data / "results.jsonl").read_text().splitlines() if l.strip()]
    wrong = [r for r in rows if r["adapter"] == args.name and not r["correct"] and not r.get("error")]
    chosen: list[dict] = []
    seen_skills: dict[str, int] = {}
    # Spread the examples over skills so the gallery shows the range of failures, not one kind.
    for row in sorted(wrong, key=lambda r: (seen_skills.get(tasks[r["task_id"]]["skill"], 0), r["task_id"])):
        skill = tasks[row["task_id"]]["skill"]
        if seen_skills.get(skill, 0) >= args.per_skill or len(chosen) >= args.limit:
            continue
        seen_skills[skill] = seen_skills.get(skill, 0) + 1
        chosen.append(row)
    image_dir = out.parent / (out.stem + "_images")
    image_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# Failure gallery: {args.name}", "",
             f"{len(wrong)} wrong answers; {len(chosen)} shown, spread over skills. Images are exactly what the model saw.", ""]
    for row in chosen:
        task = tasks[row["task_id"]]
        name = Path(task["image"]).name
        shutil.copy(data / task["image"], image_dir / name)
        d = task["difficulty"]
        lines += [f"## {row['task_id']} ({task['skill']}, {d['script']} names, {d['n_lines']} lines)", "",
                  f"![map]({image_dir.name}/{name})", "",
                  f"**Question:** {task['question']}", "",
                  f"**Model replied:** `{row['raw_reply'].strip()[:200]}`", "",
                  f"**Reference answer:** `{task['answer']}`", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} with {len(chosen)} examples")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="transitlens", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="build a validated dataset")
    g.add_argument("--out", default="out")
    g.add_argument("--maps", type=int, default=30)
    g.add_argument("--questions", type=int, default=6, help="questions per map")
    g.add_argument("--seed", type=int, default=7)
    g.add_argument("--tier", choices=["standard", "hard"], default="standard")
    g.set_defaults(func=cmd_generate)

    v = sub.add_parser("validate", help="re-derive every answer from the drawings alone")
    v.add_argument("--data", default="out")
    v.set_defaults(func=cmd_validate)

    a = sub.add_parser("audit", help="corrupt drawings and check the validator catches it")
    a.add_argument("--maps", type=int, default=20)
    a.add_argument("--seed", type=int, default=7)
    a.set_defaults(func=cmd_audit)

    e = sub.add_parser("evaluate", help="run a model over the dataset")
    e.add_argument("--data", default="out")
    e.add_argument("--adapter", choices=["oracle", "random", "gemini", "openai", "replay"], default="oracle")
    e.add_argument("--model")
    e.add_argument("--answers", help="replay: JSONL of {task_id, reply}")
    e.add_argument("--name", default="replay", help="replay: label shown in the report")
    e.add_argument("--base-url")
    e.add_argument("--workers", type=int, default=4)
    e.add_argument("--limit", type=int, default=0)
    e.add_argument("--delay", type=float, default=0.0, help="minimum seconds between calls (rate limits)")
    e.add_argument("--seed", type=int, default=0)
    e.set_defaults(func=cmd_evaluate)

    d = sub.add_parser("degrade", help="copy a dataset with lower-resolution, JPEG-compressed images")
    d.add_argument("--data", default="out")
    d.add_argument("--out", required=True)
    d.add_argument("--scale", type=float, default=0.4)
    d.add_argument("--quality", type=int, default=25)
    d.set_defaults(func=cmd_degrade)

    gl = sub.add_parser("gallery", help="write a markdown gallery of wrong answers for one run")
    gl.add_argument("--data", default="out")
    gl.add_argument("--name", required=True, help="adapter label used in results.jsonl")
    gl.add_argument("--out", default="failure_gallery.md")
    gl.add_argument("--limit", type=int, default=8)
    gl.add_argument("--per-skill", type=int, default=2)
    gl.set_defaults(func=cmd_gallery)

    r = sub.add_parser("report", help="write report.md with per-skill findings")
    r.add_argument("--data", default="out")
    r.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
