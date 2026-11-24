"""Line colour palettes. Each colour has a name that questions use to refer to the line."""

from __future__ import annotations

PALETTES: dict[str, dict[str, str]] = {
    # Familiar transit colours.
    "classic": {
        "Red": "#d62728",
        "Blue": "#1f77b4",
        "Green": "#2ca02c",
        "Orange": "#ff7f0e",
        "Purple": "#9467bd",
        "Brown": "#8c564b",
    },
    # Okabe-Ito colour-blind-safe set, so a colour-vision difference is not the reason for an error.
    "cb_safe": {
        "Red": "#d55e00",
        "Blue": "#0072b2",
        "Green": "#009e73",
        "Orange": "#e69f00",
        "Purple": "#cc79a7",
        "Brown": "#56b4e9",
    },
}

MIN_COLOUR_DISTANCE = 60.0  # RGB distance; palettes are checked against this in the tests


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def colour_distance(a: str, b: str) -> float:
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return sum((x - y) ** 2 for x, y in zip(ra, rb)) ** 0.5
