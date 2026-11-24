"""Turns a TransitMap into drawing primitives, then into an SVG and a PNG.

Both outputs come from the same primitive list, so the SVG is an exact, machine-readable
record of what is on the picture. The evidence validator parses that SVG to prove the answer
can be worked out from what is drawn alone.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont, features

from .model import Line, TransitMap

CELL = 96
MARGIN = 96
LEGEND_HEIGHT = 84
MIN_WIDTH = 640  # wide enough for the legend
SUPERSAMPLE = 2
STATION_R = 7
INTERCHANGE_R = 12
LABEL_GAP = 6
FONT_DIR = Path(__file__).parent / "fonts"  # fonts ship with the package so output is identical everywhere
LATIN_FONT = FONT_DIR / "DejaVuSans.ttf"
DEVANAGARI_FONT = FONT_DIR / "NotoSansDevanagari-Regular.ttf"
LATIN_WIDTH_FACTOR = 0.6
DEVANAGARI_WIDTH_FACTOR = 0.5
BACKGROUNDS = {"white": "#ffffff", "cream": "#fbf6e9"}
INK = "#1a1a1a"


class LegibilityError(RuntimeError):
    """The labels could not be placed without overlapping something."""


def is_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in text)


def text_width(text: str, size: int) -> float:
    """A slightly generous width estimate, used identically when placing and when parsing."""
    factor = DEVANAGARI_WIDTH_FACTOR if is_devanagari(text) else LATIN_WIDTH_FACTOR
    return factor * size * len(text)


@dataclass(frozen=True)
class Polyline:
    points: tuple[tuple[float, float], ...]
    color: str
    width: int


@dataclass(frozen=True)
class Circle:
    cx: float
    cy: float
    r: float
    fill: str
    stroke: str
    stroke_width: float


@dataclass(frozen=True)
class Text:
    x: float
    y: float
    text: str
    size: int
    anchor: str  # start | middle | end
    fill: str


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float
    fill: str


Primitive = Polyline | Circle | Text | Rect


def _grid_bounds(m: TransitMap) -> tuple[int, int, int, int]:
    xs = [s.gx for s in m.stations.values()]
    ys = [s.gy for s in m.stations.values()]
    return min(xs), min(ys), max(xs), max(ys)


def canvas_size(m: TransitMap) -> tuple[int, int]:
    """The canvas is cropped to the map, so there is no dead space to confuse a model."""
    x0, y0, x1, y1 = _grid_bounds(m)
    width = max(2 * MARGIN + (x1 - x0) * CELL, MIN_WIDTH)
    height = 2 * MARGIN + (y1 - y0) * CELL + LEGEND_HEIGHT
    return width, height


def station_xy(m: TransitMap, station_id: str) -> tuple[float, float]:
    x0, y0, _, _ = _grid_bounds(m)
    s = m.stations[station_id]
    return float(MARGIN + (s.gx - x0) * CELL), float(MARGIN + (s.gy - y0) * CELL)


def _label_box(x: float, y: float, text: str, size: int, anchor: str) -> tuple[float, float, float, float]:
    width = text_width(text, size)
    left = x if anchor == "start" else x - width if anchor == "end" else x - width / 2
    return left, y - size, left + width, y + 4  # (x0, y0, x1, y1), y is the baseline


AMBIGUITY_RATIO = 1.2  # a label's nearest marker must be clearly closer than the next one


def distance_to_box(x: float, y: float, box: tuple[float, float, float, float]) -> float:
    dx = max(box[0] - x, 0.0, x - box[2])
    dy = max(box[1] - y, 0.0, y - box[3])
    return (dx * dx + dy * dy) ** 0.5


def _boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _box_hits_circle(box: tuple[float, float, float, float], cx: float, cy: float, r: float) -> bool:
    nearest_x = min(max(cx, box[0]), box[2])
    nearest_y = min(max(cy, box[1]), box[3])
    return (nearest_x - cx) ** 2 + (nearest_y - cy) ** 2 < (r + 2) ** 2


def _box_hits_segment(
    box: tuple[float, float, float, float], p: tuple[float, float], q: tuple[float, float], pad: float
) -> bool:
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if box[0] - pad < x < box[2] + pad and box[1] - pad < y < box[3] + pad:
            return True
    return False


# Candidate label positions around a station: (dx sign, dy sign, anchor).
_PLACEMENTS = (
    (1, 0, "start"), (-1, 0, "end"), (0, -1, "middle"), (0, 1, "middle"),
    (1, -1, "start"), (1, 1, "start"), (-1, -1, "end"), (-1, 1, "end"),
)


def _unambiguous(
    m: TransitMap, sid: str, box: tuple[float, float, float, float],
    placed: dict[str, tuple[float, float, float, float]],
) -> bool:
    """A reader (or the SVG parser) must be able to tell which marker each label belongs to.

    The rule is two-way: a label is clearly nearer to its own marker than to any other marker,
    and no marker is nearer to someone else's label than to its own.
    """
    own = distance_to_box(*station_xy(m, sid), box)
    for other in m.stations:
        if other != sid and distance_to_box(*station_xy(m, other), box) < own * AMBIGUITY_RATIO:
            return False
    for other, other_box in placed.items():
        if distance_to_box(*station_xy(m, sid), other_box) < own * AMBIGUITY_RATIO:
            return False
        other_own = distance_to_box(*station_xy(m, other), other_box)
        if distance_to_box(*station_xy(m, other), box) < other_own * AMBIGUITY_RATIO:
            return False
    return True


def _place_labels(
    m: TransitMap, size: int, circle_r: dict[str, float], rng: random.Random
) -> dict[str, Text]:
    segments = [
        (station_xy(m, a), station_xy(m, b))
        for line in m.lines
        for a, b in zip(line.station_ids, line.station_ids[1:])
    ]
    placed: dict[str, tuple[float, float, float, float]] = {}
    labels: dict[str, Text] = {}
    # Busiest stations first: interchanges have the least room.
    order = sorted(m.stations, key=lambda sid: (-circle_r[sid], sid))
    offset = rng.randrange(2)  # style variation in which side is preferred
    for sid in order:
        cx, cy = station_xy(m, sid)
        name = m.stations[sid].name
        placements = list(_PLACEMENTS)
        if offset:
            placements = placements[1:2] + placements[0:1] + placements[2:]
        for dx, dy, anchor in placements:
            gap = circle_r[sid] + LABEL_GAP
            x = cx + dx * gap + (0 if dx == 0 else 0)
            y = cy + dy * (gap + size * 0.6) + (size * 0.35 if dy == 0 else 0)
            box = _label_box(x, y, name, size, anchor)
            if box[0] < 4 or box[2] > canvas_size(m)[0] - 4 or box[1] < 4:
                continue
            if any(_boxes_overlap(box, other) for other in placed.values()):
                continue
            if any(_box_hits_circle(box, *station_xy(m, other), circle_r[other]) for other in m.stations):
                continue
            if any(_box_hits_segment(box, p, q, 4) for p, q in segments):
                continue
            if not _unambiguous(m, sid, box, placed):
                continue
            placed[sid] = box
            labels[sid] = Text(x, y, name, size, anchor, INK)
            break
        else:
            raise LegibilityError(f"no free label position for {name}")
    return labels


def build_primitives(m: TransitMap) -> list[Primitive]:
    size = int(m.style.get("font_size", 14))
    width = int(m.style.get("line_width", 8))
    rng = random.Random(m.seed ^ 0x5EED)

    membership: dict[str, int] = {}
    for line in m.lines:
        for sid in line.station_ids:
            membership[sid] = membership.get(sid, 0) + 1
    circle_r = {sid: INTERCHANGE_R if membership.get(sid, 0) > 1 else STATION_R for sid in m.stations}

    prims: list[Primitive] = []
    for line in m.lines:
        pts = tuple(station_xy(m, sid) for sid in line.station_ids)
        prims.append(Polyline(pts, line.color, width))
    for sid in m.stations:
        cx, cy = station_xy(m, sid)
        is_hub = membership[sid] > 1
        prims.append(Circle(cx, cy, circle_r[sid], "#ffffff", INK, 4 if is_hub else 3))
    prims.extend(_place_labels(m, size, circle_r, rng).values())

    # Legend along the bottom: a colour swatch and the line's name.
    _, height = canvas_size(m)
    x = float(MARGIN)
    y = float(height - LEGEND_HEIGHT / 2)
    for line in m.lines:
        label = f"{line.name} Line"
        prims.append(Rect(x, y - 7, 34, 14, line.color))
        prims.append(Text(x + 44, y + 5, label, 16, "start", INK))
        x += 44 + text_width(label, 16) + 40
    return prims


def _svg_font(text: str) -> str:
    return "Noto Sans Devanagari, Mangal, sans-serif" if is_devanagari(text) else "DejaVu Sans, sans-serif"


def to_svg(m: TransitMap, prims: list[Primitive]) -> str:
    width, height = canvas_size(m)
    background = BACKGROUNDS[str(m.style.get("background", "white"))]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{background}" data-role="background"/>',
    ]
    for p in prims:
        if isinstance(p, Polyline):
            points = " ".join(f"{x:.1f},{y:.1f}" for x, y in p.points)
            out.append(
                f'<polyline points="{points}" fill="none" stroke="{p.color}" stroke-width="{p.width}" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
            )
        elif isinstance(p, Circle):
            out.append(
                f'<circle cx="{p.cx:.1f}" cy="{p.cy:.1f}" r="{p.r}" fill="{p.fill}" '
                f'stroke="{p.stroke}" stroke-width="{p.stroke_width}"/>'
            )
        elif isinstance(p, Rect):
            out.append(
                f'<rect x="{p.x:.1f}" y="{p.y:.1f}" width="{p.w}" height="{p.h}" fill="{p.fill}"/>'
            )
        else:
            out.append(
                f'<text x="{p.x:.1f}" y="{p.y:.1f}" font-size="{p.size}" text-anchor="{p.anchor}" '
                f'font-family="{_svg_font(p.text)}" fill="{p.fill}">{escape(p.text)}</text>'
            )
    out.append("</svg>")
    return "\n".join(out)


def to_png(m: TransitMap, prims: list[Primitive]) -> bytes:
    """Rasterises the primitives with anti-aliasing (drawn at 2x, then downsampled)."""
    k = SUPERSAMPLE
    width, height = canvas_size(m)
    image = Image.new("RGB", (width * k, height * k), BACKGROUNDS[str(m.style.get("background", "white"))])
    draw = ImageDraw.Draw(image)
    fonts: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}

    def font(size: int, devanagari: bool) -> ImageFont.FreeTypeFont:
        key = (size, devanagari)
        if key not in fonts:
            if devanagari:
                if not features.check("raqm"):
                    raise RuntimeError(
                        "Devanagari needs Pillow built with raqm (HarfBuzz) text shaping; "
                        "install a recent Pillow wheel"
                    )
                fonts[key] = ImageFont.truetype(
                    str(DEVANAGARI_FONT), size * k, layout_engine=ImageFont.Layout.RAQM
                )
            else:
                fonts[key] = ImageFont.truetype(str(LATIN_FONT), size * k)
        return fonts[key]

    for p in prims:
        if isinstance(p, Polyline):
            pts = [(x * k, y * k) for x, y in p.points]
            draw.line(pts, fill=p.color, width=p.width * k, joint="curve")
            r = p.width * k / 2
            for x, y in pts:  # round joins and caps
                draw.ellipse((x - r, y - r, x + r, y + r), fill=p.color)
        elif isinstance(p, Circle):
            r = p.r * k
            draw.ellipse(
                (p.cx * k - r, p.cy * k - r, p.cx * k + r, p.cy * k + r),
                fill=p.fill, outline=p.stroke, width=int(p.stroke_width * k),
            )
        elif isinstance(p, Rect):
            draw.rectangle((p.x * k, p.y * k, (p.x + p.w) * k, (p.y + p.h) * k), fill=p.fill)
        else:
            f = font(p.size, is_devanagari(p.text))
            w = f.getlength(p.text)
            x = p.x * k if p.anchor == "start" else p.x * k - w if p.anchor == "end" else p.x * k - w / 2
            draw.text((x, p.y * k), p.text, font=f, fill=p.fill, anchor="ls")
    image = image.resize((width, height), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def line_by_name(m: TransitMap, name: str) -> Line:
    return next(line for line in m.lines if line.name == name)


def write_files(m: TransitMap, directory: Path, stem: str) -> tuple[Path, Path]:
    prims = build_primitives(m)
    directory.mkdir(parents=True, exist_ok=True)
    svg_path = directory / f"{stem}.svg"
    png_path = directory / f"{stem}.png"
    svg_path.write_text(to_svg(m, prims), encoding="utf-8")
    png_path.write_bytes(to_png(m, prims))
    return svg_path, png_path
