"""Rebuilds a transit network from an SVG using only what is drawn.

It reads shapes and text, never any hidden ids or the generator's own data. If the network it
recovers gives the same answers as the reference, then the picture really does contain enough
evidence to answer the question, and a model that gets it wrong has misread the picture.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from .model import Network
from .render import AMBIGUITY_RATIO, _label_box, distance_to_box

SVG_NS = "{http://www.w3.org/2000/svg}"
VERTEX_TOLERANCE = 1.0
MAX_SWATCH_HEIGHT = 20.0


@dataclass
class ParsedMap:
    network: dict[str, tuple[str, ...]]
    issues: list[str] = field(default_factory=list)


def parse_svg(svg_text: str) -> ParsedMap:
    root = etree.fromstring(svg_text.encode("utf-8"))
    issues: list[str] = []
    canvas_w = float(root.get("width", "0"))
    canvas_h = float(root.get("height", "0"))

    rects = []
    for el in root.iter(f"{SVG_NS}rect"):
        x, y, w, h = (float(el.get(k, "0")) for k in ("x", "y", "width", "height"))
        if w >= canvas_w and h >= canvas_h:
            continue  # the background
        if h <= MAX_SWATCH_HEIGHT:
            rects.append((x, y, w, h, el.get("fill", "")))

    texts = [
        (float(el.get("x", "0")), float(el.get("y", "0")), el.text or "", int(float(el.get("font-size", "14"))), el.get("text-anchor", "start"))
        for el in root.iter(f"{SVG_NS}text")
    ]

    # Legend: each swatch is paired with the text just to its right on the same row.
    legend_texts: set[int] = set()
    colour_to_line: dict[str, str] = {}
    for x, y, w, h, fill in rects:
        row = [
            (tx - (x + w), i)
            for i, (tx, ty, content, _, _) in enumerate(texts)
            if tx >= x + w and y - 4 <= ty <= y + h + 8 and content.endswith(" Line")
        ]
        if not row:
            issues.append(f"legend swatch {fill} has no label")
            continue
        _, index = min(row)
        legend_texts.add(index)
        colour_to_line[fill.lower()] = texts[index][2].removesuffix(" Line")

    circles = [
        (float(el.get("cx", "0")), float(el.get("cy", "0")))
        for el in root.iter(f"{SVG_NS}circle")
    ]
    labels = [
        (texts[i][2], _label_box(texts[i][0], texts[i][1], texts[i][2], texts[i][3], texts[i][4]))
        for i in range(len(texts))
        if i not in legend_texts
    ]
    if len(labels) != len(circles):
        issues.append(f"{len(circles)} station markers but {len(labels)} labels")

    # Each marker takes the nearest label; every label must be taken exactly once.
    circle_name: dict[int, str] = {}
    taken: dict[int, int] = {}
    for ci, (cx, cy) in enumerate(circles):
        ranked = sorted(
            ((distance_to_box(cx, cy, box), li) for li, (_, box) in enumerate(labels))
        )
        if not ranked:
            issues.append("no labels")
            continue
        nearest, li = ranked[0]
        if len(ranked) > 1 and ranked[1][0] < nearest * AMBIGUITY_RATIO:
            issues.append(f"ambiguous label near marker at ({cx:.0f},{cy:.0f})")
        circle_name[ci] = labels[li][0]
        taken[li] = taken.get(li, 0) + 1
    if any(count != 1 for count in taken.values()) or len(taken) != len(labels):
        issues.append("labels and markers do not pair one-to-one")

    network: dict[str, tuple[str, ...]] = {}
    for el in root.iter(f"{SVG_NS}polyline"):
        colour = (el.get("stroke") or "").lower()
        line = colour_to_line.get(colour)
        if line is None:
            issues.append(f"polyline colour {colour} is not in the legend")
            continue
        names: list[str] = []
        for pair in (el.get("points") or "").split():
            px, py = (float(v) for v in pair.split(","))
            match = [
                ci for ci, (cx, cy) in enumerate(circles)
                if abs(cx - px) <= VERTEX_TOLERANCE and abs(cy - py) <= VERTEX_TOLERANCE
            ]
            if len(match) != 1 or match[0] not in circle_name:
                issues.append(f"{line} line vertex ({px:.0f},{py:.0f}) has no station marker")
                continue
            names.append(circle_name[match[0]])
        network[line] = tuple(names)
    return ParsedMap(network=network, issues=issues)
