import random

import pytest

from conftest import drawable_maps
from transitlens.model import canonical_network
from transitlens.names import SCRIPTS, draw_names, name_pool, to_devanagari
from transitlens.parse_svg import parse_svg
from transitlens.questions import generate_questions
from transitlens.render import (
    DEVANAGARI_FONT, LATIN_FONT, build_primitives, is_devanagari, text_width, to_png, to_svg,
)
from transitlens.scoring import is_correct, normalise
from transitlens.tasks import make_map, recipe_for
from transitlens.validate import raster_check, validate_task


def test_fonts_ship_with_the_package():
    assert LATIN_FONT.exists() and DEVANAGARI_FONT.exists()


def test_every_name_transliterates_and_stays_unique():
    pool = name_pool()
    converted = [to_devanagari(n) for n in pool]
    assert len(set(converted)) == len(pool)  # mapping is one to one, so answers stay unambiguous
    assert all(is_devanagari(c) and not any(ch.isascii() and ch.isalpha() for ch in c) for c in converted)


def test_script_choice_changes_only_the_spelling():
    latin = draw_names(random.Random(3), 12, "latin")
    dev = draw_names(random.Random(3), 12, "devanagari")
    assert [to_devanagari(n) for n in latin] == dev


def test_unknown_script_and_name_are_rejected():
    with pytest.raises(ValueError):
        draw_names(random.Random(0), 3, "klingon")
    with pytest.raises(ValueError):
        to_devanagari("Xyzpur")
    assert SCRIPTS == ("latin", "devanagari")


def test_devanagari_width_estimate_is_smaller_per_character():
    assert text_width("रानपुर", 14) < text_width("Ranpur", 14)


def test_devanagari_maps_round_trip_through_svg_and_png():
    count = 0
    for m, svg, png in drawable_maps(8, script="devanagari"):
        parsed = parse_svg(svg)
        assert parsed.issues == []
        assert canonical_network(parsed.network) == canonical_network(m.network())
        assert raster_check(m, png) == []
        count += 1
    assert count == 8


def test_devanagari_tasks_validate():
    for m, svg, png in drawable_maps(4, script="devanagari"):
        for q in generate_questions(m.network(), random.Random(m.seed), 6):
            assert validate_task(m, q, svg, png).passed


def test_recipe_mixes_both_scripts():
    assert {recipe_for(i).script for i in range(30)} == {"latin", "devanagari"}
    m, _ = make_map(7, 7)
    assert m.style["script"] == "devanagari"
    assert make_map(7, 0)[0].style["script"] == "latin"


def test_text_scoring_works_for_devanagari():
    assert is_correct("text", "रानपुर", " रानपुर. ")
    assert not is_correct("text", "रानपुर", "रानबाग")
    assert normalise("text", "") == ""


def test_devanagari_png_is_not_blank_text():
    # Rendering the same map with Devanagari names must draw the glyphs, not boxes of equal size.
    m, _, png = next(drawable_maps(1, script="devanagari"))
    assert len(png) > 5_000
    assert to_svg(m, build_primitives(m)).count("Noto Sans Devanagari") == len(m.stations)
