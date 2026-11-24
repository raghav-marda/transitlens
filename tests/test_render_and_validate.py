import random

from conftest import drawable_maps, make
from transitlens.model import canonical_network
from transitlens.mutate import MUTATORS, audit
from transitlens.parse_svg import parse_svg
from transitlens.questions import Question, generate_questions
from transitlens.render import LegibilityError, build_primitives, to_png, to_svg
from transitlens.validate import raster_check, validate_task


def test_svg_alone_rebuilds_the_exact_network():
    for m, svg, _ in drawable_maps(25):
        parsed = parse_svg(svg)
        assert parsed.issues == []
        assert canonical_network(parsed.network) == canonical_network(m.network())


def test_png_contains_what_the_map_says():
    for m, _, png in drawable_maps(10):
        assert raster_check(m, png) == []


def test_rendering_is_deterministic():
    m = make(5)
    try:
        prims = build_primitives(m)
    except LegibilityError:
        m = next(drawable_maps(1))[0]
        prims = build_primitives(m)
    assert to_svg(m, prims) == to_svg(m, build_primitives(m))
    assert to_png(m, prims) == to_png(m, build_primitives(m))


def test_all_generated_tasks_pass_validation():
    total = 0
    for m, svg, png in drawable_maps(12):
        for q in generate_questions(m.network(), random.Random(m.seed), 6):
            assert validate_task(m, q, svg, png).passed
            total += 1
    assert total > 50


def test_validator_rejects_a_wrong_reference_answer():
    m, svg, png = next(drawable_maps(1))
    q = generate_questions(m.network(), random.Random(0), 1)[0]
    wrong = Question(q.kind, q.skill, q.text, "99", q.answer_type, q.params)
    record = validate_task(m, wrong, svg, png)
    assert not record.passed and not record.solvers_agree


def test_validator_catches_every_injected_corruption():
    applied = caught = 0
    for m, svg, _ in drawable_maps(10):
        for name, (c, a) in audit(m, svg, random.Random(m.seed), rounds=4).items():
            caught += c
            applied += a
            assert c == a, f"missed some '{name}' corruptions"
    assert applied > 150 and caught == applied


def test_every_corruption_operator_is_exercised():
    m, svg, _ = next(drawable_maps(1, n_lines=5))
    results = audit(m, svg, random.Random(0), rounds=3)
    assert set(results) == set(MUTATORS)
    assert all(applied > 0 for _, applied in results.values())


def test_tampered_png_is_detected():
    from PIL import Image
    import io

    m, _, png = next(drawable_maps(1))
    image = Image.new("RGB", Image.open(io.BytesIO(png)).size, "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    assert raster_check(m, buffer.getvalue()) != []
