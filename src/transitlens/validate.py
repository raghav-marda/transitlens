"""Independent checks that a task is solvable and its reference answer is right.

1. Two solvers must agree (graph-of-states vs graph-of-lines).
2. The network rebuilt from the SVG alone must equal the ground truth, and give the same answer.
3. The PNG that models actually see must contain the drawn stations and line colours.
4. The map must be legible: every label placed without overlap (enforced when drawing).
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field

from PIL import Image

from .model import TransitMap, canonical_network
from .palette import colour_distance
from .parse_svg import parse_svg
from .questions import Question, answer_for
from .render import CELL, station_xy

RASTER_COLOUR_TOLERANCE = 45.0
EDGE_SAMPLE_FRACTION = 0.25  # 25% along an edge is never where two lines cross (that is 50%)


@dataclass
class ValidationRecord:
    solvers_agree: bool = False
    svg_network_matches: bool = False
    svg_answer_matches: bool = False
    raster_ok: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.solvers_agree and self.svg_network_matches
            and self.svg_answer_matches and self.raster_ok and not self.issues
        )

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "passed": self.passed}


def raster_check(m: TransitMap, png: bytes) -> list[str]:
    """Samples the PNG: station markers are white, and line colours appear along every edge."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    problems: list[str] = []
    for sid, station in m.stations.items():
        x, y = station_xy(m, sid)
        if sum(image.getpixel((int(x), int(y)))) < 3 * 235:
            problems.append(f"marker for {station.name} is not drawn")
    for line in m.lines:
        for a, b in zip(line.station_ids, line.station_ids[1:]):
            (ax, ay), (bx, by) = station_xy(m, a), station_xy(m, b)
            t = EDGE_SAMPLE_FRACTION
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            r, g, bl = image.getpixel((int(px), int(py)))
            if colour_distance(f"#{r:02x}{g:02x}{bl:02x}", line.color) > RASTER_COLOUR_TOLERANCE:
                problems.append(f"{line.name} line is not drawn near {m.stations[a].name}")
    return problems


def validate_task(m: TransitMap, question: Question, svg: str, png: bytes) -> ValidationRecord:
    record = ValidationRecord()
    truth = m.network()

    try:
        record.solvers_agree = answer_for(question.kind, question.params, truth) == question.answer
    except AssertionError as error:
        record.issues.append(str(error))

    parsed = parse_svg(svg)
    record.issues.extend(parsed.issues)
    record.svg_network_matches = canonical_network(parsed.network) == canonical_network(truth)
    if not record.svg_network_matches:
        record.issues.append("network rebuilt from the SVG differs from the ground truth")
    try:
        record.svg_answer_matches = answer_for(question.kind, question.params, parsed.network) == question.answer
    except (KeyError, ValueError, AssertionError, IndexError) as error:
        record.issues.append(f"answer not derivable from the drawing: {error!r}")

    record.issues.extend(raster_check(m, png))
    record.raster_ok = not any("drawn" in issue for issue in record.issues)
    return record
