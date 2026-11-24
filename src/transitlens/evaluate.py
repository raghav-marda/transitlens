"""Runs an adapter over a dataset and records every reply. Resumable and parallel."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .adapters import Adapter
from .scoring import is_correct, normalise


def _run_one(adapter: Adapter, data_dir: Path, task: dict[str, object]) -> dict[str, object]:
    png = (data_dir / str(task["image"])).read_bytes()
    started = time.monotonic()
    try:
        raw, error = adapter.answer(task, png), None
    except Exception as exc:  # a failed call is recorded, never silently counted as wrong
        raw, error = "", f"{type(exc).__name__}: {exc}"[:300]
    answer_type = str(task["answer_type"])
    return {
        "task_id": task["task_id"],
        "adapter": adapter.name,
        "raw_reply": raw,
        "parsed": normalise(answer_type, raw),
        "reference": task["answer"],
        "correct": error is None and is_correct(answer_type, str(task["answer"]), raw),
        "error": error,
        "seconds": round(time.monotonic() - started, 2),
    }


def evaluate(
    adapter: Adapter, data_dir: Path, tasks: list[dict[str, object]], results_path: Path, workers: int = 4
) -> list[dict[str, object]]:
    done: dict[str, dict[str, object]] = {}
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("adapter") == adapter.name and not row.get("error"):
                    done[str(row["task_id"])] = row
    pending = [t for t in tasks if str(t["task_id"]) not in done]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        fresh = list(pool.map(lambda t: _run_one(adapter, data_dir, t), pending))
    rows = list(done.values()) + fresh
    results_path.parent.mkdir(parents=True, exist_ok=True)
    others: list[str] = []
    if results_path.exists():
        others = [
            line for line in results_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("adapter") != adapter.name
        ]
    with results_path.open("w", encoding="utf-8") as handle:
        for line in others:
            handle.write(line + "\n")
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows
