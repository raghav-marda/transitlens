"""Turns a model's free-text reply into a comparable answer, then scores it."""

from __future__ import annotations

import math
import re
import unicodedata

_INTEGER = re.compile(r"-?\d+")
_WORDS = re.compile(r"[A-Za-z]+")
_LINE_COLOURS = {"red", "blue", "green", "orange", "purple", "brown"}


def normalise(answer_type: str, raw: str) -> str:
    text = raw.strip()
    if answer_type == "int":
        if "impossible" in text.lower():
            return "impossible"
        numbers = _INTEGER.findall(text)
        return numbers[-1] if numbers else ""
    if answer_type == "set":
        found = {w.lower() for w in _WORDS.findall(text)} & _LINE_COLOURS
        return ", ".join(sorted(c.capitalize() for c in found))
    # Station names: compare letters, marks and digits only, so the same name in Latin or
    # Devanagari matches itself regardless of case, spacing or punctuation.
    folded = unicodedata.normalize("NFC", text).casefold()
    return "".join(ch for ch in folded if unicodedata.category(ch)[0] in "LMN")


def is_correct(answer_type: str, reference: str, raw_reply: str) -> bool:
    return normalise(answer_type, raw_reply) == normalise(answer_type, reference)


def wilson_interval(correct: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for an accuracy measured on `total` tasks."""
    if total == 0:
        return 0.0, 0.0
    p = correct / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)
