"""Invented station names.

Names are made up on purpose: with real station names a model could answer from memory of
a real network. Invented names force it to read the picture.
"""

from __future__ import annotations

import random

_PREFIXES = (
    "Ran", "Kal", "Mor", "Tar", "Ved", "Nil", "Sur", "Pran", "Har", "Ind", "Dev", "Mand",
    "Chan", "Lak", "Sham", "Bhav", "Gan", "Jai", "Kes", "Mit", "Nav", "Pad", "Raj", "Sat",
    "Tul", "Uma", "Vik", "Yam", "Asha", "Bal", "Dan", "Eka", "Fat", "Gul", "Him", "Isha",
)
_SUFFIXES = ("pur", "bagh", "gate", "chowk", "vihar", "ganj", "wadi", "kunj", "nagar", "pet")

MAX_NAME_LENGTH = 10

SCRIPTS = ("latin", "devanagari")

# One fixed Devanagari spelling per syllable, so a map has the same station in either script.
_PREFIXES_DEV = {
    "Ran": "रान", "Kal": "काल", "Mor": "मोर", "Tar": "तार", "Ved": "वेद", "Nil": "नील",
    "Sur": "सुर", "Pran": "प्रान", "Har": "हर", "Ind": "इंद", "Dev": "देव", "Mand": "मंद",
    "Chan": "चंद", "Lak": "लक", "Sham": "शाम", "Bhav": "भाव", "Gan": "गण", "Jai": "जय",
    "Kes": "केस", "Mit": "मित", "Nav": "नव", "Pad": "पद", "Raj": "राज", "Sat": "सत",
    "Tul": "तुल", "Uma": "उमा", "Vik": "विक", "Yam": "यम", "Asha": "आशा", "Bal": "बल",
    "Dan": "दान", "Eka": "एक", "Fat": "फत", "Gul": "गुल", "Him": "हिम", "Isha": "ईशा",
}
_SUFFIXES_DEV = {
    "pur": "पुर", "bagh": "बाग", "gate": "गेट", "chowk": "चौक", "vihar": "विहार",
    "ganj": "गंज", "wadi": "वाड़ी", "kunj": "कुंज", "nagar": "नगर", "pet": "पेठ",
}

def name_pool() -> list[str]:
    pool = [p + s for p in _PREFIXES for s in _SUFFIXES]
    return [n for n in pool if len(n) <= MAX_NAME_LENGTH]


def to_devanagari(name: str) -> str:
    """Spells a generated Latin name in Devanagari (prefix + suffix, each mapped one to one)."""
    for prefix, dev_prefix in _PREFIXES_DEV.items():
        if name.startswith(prefix):
            suffix = name[len(prefix):]
            if suffix in _SUFFIXES_DEV:
                return dev_prefix + _SUFFIXES_DEV[suffix]
    raise ValueError(f"cannot transliterate {name!r}")


def draw_names(rng: random.Random, count: int, script: str = "latin") -> list[str]:
    if script not in SCRIPTS:
        raise ValueError(f"unknown script {script!r}")
    pool = name_pool()
    if count > len(pool):
        raise ValueError("not enough station names")
    chosen = rng.sample(pool, count)
    return chosen if script == "latin" else [to_devanagari(n) for n in chosen]
