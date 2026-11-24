import random

import pytest

from transitlens.layout import LayoutParams, build_map
from transitlens.render import LegibilityError, build_primitives, to_png, to_svg

STYLE = {"font_size": 14, "line_width": 8, "background": "white"}


def make(seed: int, **overrides):
    params = LayoutParams(**overrides)
    return build_map(seed, params, dict(STYLE))


def drawable_maps(count: int, start: int = 0, **overrides):
    """Yields (map, svg, png) for the first `count` seeds whose labels can be placed legibly."""
    found = 0
    seed = start
    while found < count and seed < start + 500:
        m = make(seed, **overrides)
        seed += 1
        try:
            prims = build_primitives(m)
        except LegibilityError:
            continue
        found += 1
        yield m, to_svg(m, prims), to_png(m, prims)


@pytest.fixture
def rng():
    return random.Random(1234)
