"""Deliberately corrupts SVGs to prove the validator notices when a drawing stops matching its map.

A validator that has never been shown a bad drawing proves nothing. Each operator below damages a
good drawing in a way that would change a reference answer or make a label ambiguous; the audit
reports what fraction the validator catches.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from lxml import etree

from .model import TransitMap, canonical_network
from .parse_svg import SVG_NS, parse_svg

Mutator = Callable[[etree._Element, random.Random], bool]


def _drop_marker(root: etree._Element, rng: random.Random) -> bool:
    circles = list(root.iter(f"{SVG_NS}circle"))
    if not circles:
        return False
    victim = rng.choice(circles)
    victim.getparent().remove(victim)
    return True


def _swap_labels(root: etree._Element, rng: random.Random) -> bool:
    texts = [t for t in root.iter(f"{SVG_NS}text") if not (t.text or "").endswith(" Line")]
    if len(texts) < 2:
        return False
    a, b = rng.sample(texts, 2)
    a.text, b.text = b.text, a.text
    return True


def _recolour_line(root: etree._Element, rng: random.Random) -> bool:
    lines = list(root.iter(f"{SVG_NS}polyline"))
    colours = sorted({line.get("stroke") for line in lines})
    if len(lines) < 2 or len(colours) < 2:
        return False
    victim = rng.choice(lines)
    victim.set("stroke", rng.choice([c for c in colours if c != victim.get("stroke")]))
    return True


def _drop_vertex(root: etree._Element, rng: random.Random) -> bool:
    lines = [line for line in root.iter(f"{SVG_NS}polyline") if len((line.get("points") or "").split()) > 3]
    if not lines:
        return False
    victim = rng.choice(lines)
    points = victim.get("points", "").split()
    del points[rng.randrange(1, len(points) - 1)]
    victim.set("points", " ".join(points))
    return True


def _shift_label(root: etree._Element, rng: random.Random) -> bool:
    texts = [t for t in root.iter(f"{SVG_NS}text") if not (t.text or "").endswith(" Line")]
    if not texts:
        return False
    victim = rng.choice(texts)
    victim.set("x", str(float(victim.get("x", "0")) + 600))
    return True


MUTATORS: dict[str, Mutator] = {
    "remove a station marker": _drop_marker,
    "swap two station names": _swap_labels,
    "recolour a line": _recolour_line,
    "delete a stop from a line": _drop_vertex,
    "move a label away from its marker": _shift_label,
}


def is_caught(m: TransitMap, svg: str) -> bool:
    """True if the parser's view of the drawing no longer equals the ground truth, or it flags a problem."""
    parsed = parse_svg(svg)
    return bool(parsed.issues) or canonical_network(parsed.network) != canonical_network(m.network())


def audit(m: TransitMap, svg: str, rng: random.Random, rounds: int = 5) -> dict[str, tuple[int, int]]:
    """For each operator: (corruptions caught, corruptions applied)."""
    results: dict[str, tuple[int, int]] = {}
    for name, mutator in MUTATORS.items():
        caught = applied = 0
        for _ in range(rounds):
            root = etree.fromstring(svg.encode("utf-8"))
            if not mutator(root, rng):
                continue
            applied += 1
            caught += is_caught(m, etree.tostring(root, encoding="unicode"))
        results[name] = (caught, applied)
    return results
