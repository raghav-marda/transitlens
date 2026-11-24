"""Aggregates results into the findings a reader needs: where a model is strong and where it fails."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .scoring import wilson_interval

LOW_N = 20  # below this many tasks a bucket is flagged: its interval is too wide to rank on


def _bucket_rows(
    tasks: dict[str, dict[str, object]], rows: list[dict[str, object]], key
) -> dict[str, tuple[int, int]]:
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        task = tasks[str(row["task_id"])]
        bucket = str(key(task))
        totals[bucket][1] += 1
        totals[bucket][0] += 1 if row["correct"] else 0
    return {k: (v[0], v[1]) for k, v in totals.items()}


def summarise(tasks_list: list[dict[str, object]], rows: list[dict[str, object]]) -> dict[str, object]:
    tasks = {str(t["task_id"]): t for t in tasks_list}
    errors = sum(1 for r in rows if r.get("error"))
    scored = [r for r in rows if not r.get("error")]

    def section(key) -> list[dict[str, object]]:
        out = []
        for bucket, (correct, total) in sorted(_bucket_rows(tasks, scored, key).items()):
            low, high = wilson_interval(correct, total)
            out.append({
                "bucket": bucket, "correct": correct, "total": total,
                "accuracy": round(correct / total, 3) if total else 0.0,
                "ci95": [round(low, 3), round(high, 3)], "low_n": total < LOW_N,
            })
        return out

    def crossing_band(t: dict[str, object]) -> str:
        d = t["difficulty"]  # type: ignore[index]
        return "with station-less crossings" if d["n_crossings"] > 0 else "no crossings"  # type: ignore[index]

    def lines_band(t: dict[str, object]) -> str:
        return f"{t['difficulty']['n_lines']} lines"  # type: ignore[index]

    total_correct = sum(1 for r in scored if r["correct"])
    low, high = wilson_interval(total_correct, len(scored))
    wrong = [r for r in scored if not r["correct"]]
    off_by_one = sum(
        1 for r in wrong
        if tasks[str(r["task_id"])]["answer_type"] == "int"
        and str(r["parsed"]).lstrip("-").isdigit() and str(r["reference"]).isdigit()
        and abs(int(str(r["parsed"])) - int(str(r["reference"]))) == 1
    )
    return {
        "tasks_scored": len(scored),
        "call_errors": errors,
        "accuracy": round(total_correct / len(scored), 3) if scored else 0.0,
        "ci95": [round(low, 3), round(high, 3)],
        "wrong": len(wrong),
        "wrong_off_by_one": off_by_one,
        "by_skill": section(lambda t: t["skill"]),
        "by_kind": section(lambda t: t["kind"]),
        "by_crossings": section(crossing_band),
        "by_lines": section(lines_band),
        "by_palette": section(lambda t: t["difficulty"]["palette"]),  # type: ignore[index]
        "by_script": section(lambda t: t["difficulty"].get("script", "latin")),  # type: ignore[union-attr]
    }


def to_markdown(name: str, summary: dict[str, object]) -> str:
    lines = [f"## {name}", ""]
    lines.append(
        f"Overall accuracy **{summary['accuracy']:.1%}** on {summary['tasks_scored']} tasks "
        f"(95% CI {summary['ci95'][0]:.1%} to {summary['ci95'][1]:.1%}); "  # type: ignore[index]
        f"{summary['call_errors']} failed calls excluded."
    )
    for title, key in (("By skill", "by_skill"), ("By question kind", "by_kind"),
                       ("By station-less crossings", "by_crossings"), ("By number of lines", "by_lines"),
                       ("By colour palette", "by_palette"),
                       ("By station-name script", "by_script")):
        lines += ["", f"### {title}", "", "| Bucket | Correct / total | Accuracy | 95% CI | Note |", "|---|---|---|---|---|"]
        for b in summary[key]:  # type: ignore[union-attr]
            note = "low n, do not rank" if b["low_n"] else ""
            lines.append(
                f"| {b['bucket']} | {b['correct']}/{b['total']} | {b['accuracy']:.1%} | "
                f"{b['ci95'][0]:.0%} to {b['ci95'][1]:.0%} | {note} |"
            )
    return "\n".join(lines) + "\n"


def write_report(data_dir: Path, results_path: Path, out_path: Path, tasks: list[dict[str, object]]) -> str:
    by_adapter: dict[str, list[dict[str, object]]] = defaultdict(list)
    for line in results_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            by_adapter[str(row["adapter"])].append(row)
    parts = ["# TransitLens evaluation report", ""]
    payload = {}
    for adapter, rows in sorted(by_adapter.items()):
        summary = summarise(tasks, rows)
        payload[adapter] = summary
        parts.append(to_markdown(adapter, summary))
    out_path.write_text("\n".join(parts), encoding="utf-8")
    out_path.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return "\n".join(parts)
