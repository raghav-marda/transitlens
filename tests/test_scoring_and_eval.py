import json
from pathlib import Path

import pytest

from transitlens.adapters import Adapter, OracleAdapter, RandomAdapter
from transitlens.cli import main
from transitlens.evaluate import evaluate
from transitlens.report import summarise, write_report
from transitlens.scoring import is_correct, normalise, wilson_interval
from transitlens.tasks import build_dataset, load_tasks


@pytest.mark.parametrize(
    "answer_type, raw, expected",
    [
        ("int", "3", "3"),
        ("int", "The answer is 2.", "2"),
        ("int", "Impossible - no route", "impossible"),
        ("int", "", ""),
        ("set", "Red and Blue", "Blue, Red"),
        ("set", "blue, RED, red", "Blue, Red"),
        ("text", " Ran-pur! ", "ranpur"),
    ],
)
def test_normalise(answer_type, raw, expected):
    assert normalise(answer_type, raw) == expected


def test_is_correct_is_format_tolerant_but_not_value_tolerant():
    assert is_correct("set", "Brown, Red", "red & brown")
    assert not is_correct("set", "Brown, Red", "Red")
    assert not is_correct("int", "2", "3")


def test_wilson_interval_properties():
    assert wilson_interval(0, 0) == (0.0, 0.0)
    low, high = wilson_interval(18, 20)
    assert 0 < low < 0.9 < high <= 1
    assert wilson_interval(20, 20)[1] == 1.0
    narrow = wilson_interval(900, 1000)
    wide = wilson_interval(9, 10)
    assert narrow[1] - narrow[0] < wide[1] - wide[0]


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("ds")
    build_dataset(out, 6, 6, seed=11)
    return out


def test_dataset_files_and_manifest(dataset):
    manifest = json.loads((dataset / "manifest.json").read_text())
    tasks = load_tasks(dataset)
    assert manifest["tasks"] == len(tasks) > 20
    assert len(manifest["skills_covered"]) == 6
    for task in tasks:
        assert (dataset / task["image"]).exists() and (dataset / task["svg"]).exists()
        assert task["validation"]["passed"] is True


def test_dataset_generation_is_reproducible(tmp_path):
    build_dataset(tmp_path / "a", 3, 4, seed=5)
    build_dataset(tmp_path / "b", 3, 4, seed=5)
    assert (tmp_path / "a" / "tasks.jsonl").read_text() == (tmp_path / "b" / "tasks.jsonl").read_text()


def test_maps_actually_vary(dataset):
    tasks = load_tasks(dataset)
    shapes = {(t["difficulty"]["n_lines"], t["difficulty"]["n_stations"], t["difficulty"]["n_crossings"]) for t in tasks}
    assert len(shapes) >= 4
    assert len({t["difficulty"]["palette"] for t in tasks}) == 2 or len({t["map_id"] for t in tasks}) < 4


def test_oracle_solves_everything_and_random_does_not(dataset, tmp_path):
    tasks = load_tasks(dataset)
    rows = evaluate(OracleAdapter(dataset), dataset, tasks, tmp_path / "r.jsonl")
    assert all(r["correct"] for r in rows)
    rows = evaluate(RandomAdapter(1), dataset, tasks, tmp_path / "r.jsonl")
    assert sum(r["correct"] for r in rows) / len(rows) < 0.3


class Counting(Adapter):
    name = "counting"

    def __init__(self):
        self.calls = 0

    def answer(self, task, png):
        self.calls += 1
        return task["answer"]


class Flaky(Adapter):
    name = "flaky"

    def answer(self, task, png):
        raise TimeoutError("boom")


def test_evaluation_is_resumable(dataset, tmp_path):
    tasks = load_tasks(dataset)
    adapter = Counting()
    evaluate(adapter, dataset, tasks, tmp_path / "r.jsonl", workers=2)
    first = adapter.calls
    evaluate(adapter, dataset, tasks, tmp_path / "r.jsonl", workers=2)
    assert first == len(tasks) and adapter.calls == first


def test_failed_calls_are_recorded_not_counted_correct(dataset, tmp_path):
    tasks = load_tasks(dataset)[:5]
    rows = evaluate(Flaky(), dataset, tasks, tmp_path / "r.jsonl")
    assert all(r["error"] and not r["correct"] for r in rows)
    summary = summarise(tasks, rows)
    assert summary["call_errors"] == 5 and summary["tasks_scored"] == 0


def test_results_of_different_models_coexist(dataset, tmp_path):
    tasks = load_tasks(dataset)
    path = tmp_path / "r.jsonl"
    evaluate(OracleAdapter(dataset), dataset, tasks, path)
    evaluate(RandomAdapter(2), dataset, tasks, path)
    names = {json.loads(line)["adapter"] for line in path.read_text().splitlines()}
    assert names == {"oracle", "random"}


def test_report_flags_small_buckets(dataset, tmp_path):
    tasks = load_tasks(dataset)
    evaluate(OracleAdapter(dataset), dataset, tasks, dataset / "results.jsonl")
    text = write_report(dataset, dataset / "results.jsonl", tmp_path / "report.md", tasks)
    assert "low n, do not rank" in text
    assert "95% CI" in text
    assert (tmp_path / "report.json").exists()


def test_cli_end_to_end(tmp_path, capsys):
    out = str(tmp_path / "cli")
    assert main(["generate", "--out", out, "--maps", "3", "--questions", "4", "--seed", "2"]) == 0
    assert main(["validate", "--data", out]) == 0
    assert main(["evaluate", "--data", out, "--adapter", "oracle"]) == 0
    assert main(["report", "--data", out]) == 0
    assert "oracle" in capsys.readouterr().out


def test_degrade_keeps_tasks_and_shrinks_images(tmp_path):
    from PIL import Image

    from transitlens.cli import main

    source, target = tmp_path / "src", tmp_path / "low"
    assert main(["generate", "--out", str(source), "--maps", "2", "--questions", "2", "--seed", "3"]) == 0
    assert main(["degrade", "--data", str(source), "--out", str(target), "--scale", "0.5", "--quality", "30"]) == 0
    assert (source / "tasks.jsonl").read_text() == (target / "tasks.jsonl").read_text()
    for path in (source / "images").glob("*.png"):
        with Image.open(path) as full, Image.open(target / "images" / path.name) as low:
            assert low.width == round(full.width * 0.5)
    assert '"scale": 0.5' in (target / "manifest.json").read_text()


def test_gallery_lists_only_wrong_answers(tmp_path):
    import json

    from transitlens.cli import main

    data = tmp_path / "data"
    assert main(["generate", "--out", str(data), "--maps", "2", "--questions", "3", "--seed", "5"]) == 0
    assert main(["evaluate", "--data", str(data), "--adapter", "random", "--seed", "1"]) == 0
    out = tmp_path / "gallery.md"
    assert main(["gallery", "--data", str(data), "--name", "random", "--out", str(out), "--limit", "3"]) == 0
    text = out.read_text()
    rows = [json.loads(line) for line in (data / "results.jsonl").read_text().splitlines()]
    wrong = [r for r in rows if not r["correct"]]
    assert f"{len(wrong)} wrong answers" in text
    assert text.count("**Reference answer:**") <= 3
