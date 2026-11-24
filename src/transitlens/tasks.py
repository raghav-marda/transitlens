"""Builds a dataset of validated tasks: maps, questions, reference answers, validation evidence."""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import GENERATOR_VERSION
from .layout import LayoutError, LayoutParams, build_map, count_crossings
from .model import TransitMap
from .questions import SKILLS, generate_questions
from .render import LegibilityError, build_primitives, to_png, to_svg
from .validate import validate_task

MAX_MAP_ATTEMPTS = 200
GRID_SIZES = ((12, 8), (14, 9))
FONT_SIZES = (13, 15)
LINE_WIDTHS = (6, 9)
BACKGROUNDS = ("white", "cream")
PALETTES = ("classic", "cb_safe")
SCRIPTS = ("latin", "devanagari")
TIERS = ("standard", "hard")
HARD_GRIDS = ((18, 11), (20, 12))


@dataclass(frozen=True)
class MapRecipe:
    """One point in the variation grid. Maps differ in structure, not in wording."""

    n_lines: int
    palette: str
    want_crossing: bool
    grid: tuple[int, int]
    font_size: int
    line_width: int
    background: str
    script: str
    tier: str = "standard"
    min_stations: int = 5
    max_stations: int = 8


def recipe_for(index: int, tier: str = "standard") -> MapRecipe:
    if tier == "hard":
        # Denser maps: 5-6 lines, longer lines, more interchanges and station-less crossings.
        return MapRecipe(
            n_lines=5 + index % 2, palette=PALETTES[(index // 2) % 2], want_crossing=True,
            grid=HARD_GRIDS[(index // 4) % 2], font_size=13, line_width=LINE_WIDTHS[(index // 3) % 2],
            background=BACKGROUNDS[(index // 6) % 2], script=SCRIPTS[(index // 7) % 2],
            tier="hard", min_stations=8, max_stations=12,
        )
    return MapRecipe(
        n_lines=3 + index % 3,
        palette=PALETTES[(index // 3) % 2],
        want_crossing=index % 2 == 0,
        grid=GRID_SIZES[(index // 2) % 2],
        font_size=FONT_SIZES[(index // 4) % 2],
        line_width=LINE_WIDTHS[(index // 5) % 2],
        background=BACKGROUNDS[(index // 6) % 2],
        script=SCRIPTS[(index // 7) % 2],
    )


def difficulty(m: TransitMap) -> dict[str, object]:
    paths = [[(m.stations[s].gx, m.stations[s].gy) for s in line.station_ids] for line in m.lines]
    return {
        "n_lines": len(m.lines),
        "n_stations": len(m.stations),
        "n_interchanges": len(m.interchange_names()),
        "n_crossings": count_crossings(paths),  # lines that cross with no station: distractors
        "palette": m.style["palette"],
        "background": m.style["background"],
        "script": m.style["script"],
        "font_size": m.style["font_size"],
        "line_width": m.style["line_width"],
    }


def make_map(seed: int, index: int, tier: str = "standard") -> tuple[TransitMap, int]:
    """First valid map for this recipe. Returns the map and how many candidates were rejected."""
    recipe = recipe_for(index, tier)
    params = LayoutParams(
        n_lines=recipe.n_lines, grid_w=recipe.grid[0], grid_h=recipe.grid[1],
        palette=recipe.palette, want_crossing=recipe.want_crossing, script=recipe.script,
    )
    style = {"font_size": recipe.font_size, "line_width": recipe.line_width, "background": recipe.background}
    rejected = 0
    # Prefer the recipe's crossing setting; fall back to the other one if no candidate is legible.
    for want_crossing in (recipe.want_crossing, not recipe.want_crossing):
        params = LayoutParams(
            n_lines=recipe.n_lines, grid_w=recipe.grid[0], grid_h=recipe.grid[1],
            palette=recipe.palette, want_crossing=want_crossing, script=recipe.script,
            min_stations=recipe.min_stations, max_stations=recipe.max_stations,
        )
        for attempt in range(MAX_MAP_ATTEMPTS):
            candidate_seed = seed * 1_000_003 + index * 1009 + attempt
            try:
                m = build_map(candidate_seed, params, dict(style))
                build_primitives(m)
            except (LayoutError, LegibilityError):
                rejected += 1
                continue
            return m, rejected
    raise LayoutError(f"no valid map for recipe {index}")


def build_dataset(out_dir: Path, n_maps: int, questions_per_map: int, seed: int, tier: str = "standard") -> dict[str, object]:
    images, maps = out_dir / "images", out_dir / "maps"
    images.mkdir(parents=True, exist_ok=True)
    maps.mkdir(parents=True, exist_ok=True)
    tasks: list[dict[str, object]] = []
    rejected_maps = 0
    rejected_tasks = 0

    for index in range(n_maps):
        m, rejected = make_map(seed, index, tier)
        rejected_maps += rejected
        prims = build_primitives(m)
        svg, png = to_svg(m, prims), to_png(m, prims)
        stem = f"m{index:04d}"
        (maps / f"{stem}.svg").write_text(svg, encoding="utf-8")
        (images / f"{stem}.png").write_bytes(png)

        rng = random.Random(seed * 7919 + index)
        for number, question in enumerate(generate_questions(m.network(), rng, questions_per_map)):
            record = validate_task(m, question, svg, png)
            if not record.passed:
                rejected_tasks += 1
                continue
            tasks.append({
                "task_id": f"{stem}-{number}",
                "map_id": stem,
                "image": f"images/{stem}.png",
                "svg": f"maps/{stem}.svg",
                "question": question.text,
                "answer": question.answer,
                "answer_type": question.answer_type,
                "kind": question.kind,
                "skill": question.skill,
                "params": question.params,
                "difficulty": difficulty(m),
                "validation": record.to_dict(),
            })

    with (out_dir / "tasks.jsonl").open("w", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")

    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "tier": tier,
        "maps": n_maps,
        "tasks": len(tasks),
        "rejected_map_candidates": rejected_maps,
        "rejected_tasks": rejected_tasks,
        "by_skill": dict(Counter(str(t["skill"]) for t in tasks)),
        "by_kind": dict(Counter(str(t["kind"]) for t in tasks)),
        "skills_covered": [s for s in SKILLS if any(t["skill"] == s for t in tasks)],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_tasks(data_dir: Path) -> list[dict[str, object]]:
    with (data_dir / "tasks.jsonl").open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
