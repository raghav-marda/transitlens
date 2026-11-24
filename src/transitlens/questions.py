"""Question types, each tagged with the visual skill it exercises.

A question is only produced when its answer is unique and well defined on the map.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .model import Network
from .solve import (
    lines_at,
    min_interchanges_a,
    min_interchanges_b,
    shared_stations,
    stations_between,
)

IMPOSSIBLE = "impossible"

SKILLS = (
    "route_planning",
    "counterfactual_reasoning",
    "interchange_identification",
    "line_tracing",
    "legend_matching",
    "counting",
)


@dataclass(frozen=True)
class Question:
    kind: str
    skill: str
    text: str
    answer: str
    answer_type: str  # int | set | text
    params: dict[str, object] = field(default_factory=dict)


def _int_answer(value: int | None) -> str:
    return IMPOSSIBLE if value is None else str(value)


def _agree(a: int | None, b: int | None) -> int | None:
    if a != b:
        raise AssertionError(f"solvers disagree: {a} vs {b}")
    return a


def q_interchange_count(net: Network, rng: random.Random, target: int | None = None) -> Question | None:
    stations = sorted({s for line in net.values() for s in line})
    for _ in range(200):
        a, b = rng.sample(stations, 2)
        value = _agree(min_interchanges_a(net, a, b), min_interchanges_b(net, a, b))
        if value is None or (target is not None and value != target):
            continue
        return Question(
            "interchange_count", "route_planning",
            f"What is the minimum number of interchanges (changes of line) needed to travel "
            f"from {a} to {b}? Answer with a number.",
            str(value), "int", {"from": a, "to": b},
        )
    return None


def q_reroute(net: Network, rng: random.Random) -> Question | None:
    stations = sorted({s for line in net.values() for s in line})
    for _ in range(300):
        closed = rng.choice(sorted(net))
        a, b = rng.sample(stations, 2)
        open_lines = {n: s for n, s in net.items() if n != closed}
        if not lines_at(open_lines, a) or not lines_at(open_lines, b):
            continue  # start or end would be served only by the closed line
        value = _agree(min_interchanges_a(net, a, b, {closed}), min_interchanges_b(net, a, b, {closed}))
        base = min_interchanges_a(net, a, b)
        if value == base:
            continue  # the closure must matter, otherwise it is a distractor with no effect
        return Question(
            "reroute", "counterfactual_reasoning",
            f"Suppose the {closed} Line is closed and cannot be used at all. What is the minimum "
            f"number of interchanges needed to travel from {a} to {b}? Answer with a number, or "
            f"the word 'impossible' if there is no route.",
            _int_answer(value), "int", {"closed": closed, "from": a, "to": b},
        )
    return None


def q_lines_at(net: Network, rng: random.Random, hubs_only: bool = True) -> Question | None:
    stations = sorted({s for line in net.values() for s in line})
    pool = [s for s in stations if len(lines_at(net, s)) >= 2] if hubs_only else stations
    if not pool:
        return None
    station = rng.choice(pool)
    answer = ", ".join(lines_at(net, station))
    return Question(
        "lines_at", "interchange_identification",
        f"Which lines stop at {station}? List every line colour, separated by commas.",
        answer, "set", {"station": station},
    )


def q_stops_between(net: Network, rng: random.Random) -> Question | None:
    options = [name for name, stations in net.items() if len(stations) >= 5]
    if not options:
        return None
    line = rng.choice(sorted(options))
    stations = list(net[line])
    i, j = sorted(rng.sample(range(len(stations)), 2))
    if j - i < 3:
        j = min(len(stations) - 1, i + 3)
        if j - i < 3:
            return None
    a, b = stations[i], stations[j]
    return Question(
        "stops_between", "line_tracing",
        f"On the {line} Line, how many stations are strictly between {a} and {b}? "
        f"Do not count {a} or {b}. Answer with a number.",
        str(stations_between(net, line, a, b)), "int", {"line": line, "from": a, "to": b},
    )


def q_connecting_station(net: Network, rng: random.Random) -> Question | None:
    pairs = [
        (x, y)
        for x in sorted(net) for y in sorted(net)
        if x < y and len(shared_stations(net, x, y)) == 1
    ]
    if not pairs:
        return None
    x, y = rng.choice(pairs)
    return Question(
        "connecting_station", "legend_matching",
        f"At which station do the {x} Line and the {y} Line meet? Answer with the station name.",
        shared_stations(net, x, y)[0], "text", {"lines": [x, y]},
    )


def q_line_length(net: Network, rng: random.Random) -> Question | None:
    line = rng.choice(sorted(net))
    return Question(
        "line_length", "counting",
        f"How many stations are on the {line} Line, including both end stations? Answer with a number.",
        str(len(net[line])), "int", {"line": line},
    )


def generate_questions(net: Network, rng: random.Random, count: int) -> list[Question]:
    """A varied mix: one of each kind first, then more route-planning, the hardest kind."""
    makers = [
        lambda: q_interchange_count(net, rng),
        lambda: q_reroute(net, rng),
        lambda: q_lines_at(net, rng),
        lambda: q_stops_between(net, rng),
        lambda: q_connecting_station(net, rng),
        lambda: q_line_length(net, rng),
    ]
    out: list[Question] = []
    seen: set[str] = set()
    index = 0
    guard = 0
    while len(out) < count and guard < count * 20:
        guard += 1
        question = makers[index % len(makers)]()
        index += 1
        if question is not None and question.text not in seen:
            seen.add(question.text)
            out.append(question)
    return out


def answer_for(kind: str, params: dict[str, object], net: Network) -> str:
    """Recomputes a question's answer from its parameters and a network.

    The validators call this on a network rebuilt from the SVG alone, which proves that the
    drawing itself carries enough evidence to reach the reference answer.
    """
    if kind == "interchange_count":
        a, b = str(params["from"]), str(params["to"])
        return _int_answer(_agree(min_interchanges_a(net, a, b), min_interchanges_b(net, a, b)))
    if kind == "reroute":
        a, b, closed = str(params["from"]), str(params["to"]), str(params["closed"])
        return _int_answer(
            _agree(min_interchanges_a(net, a, b, {closed}), min_interchanges_b(net, a, b, {closed}))
        )
    if kind == "lines_at":
        return ", ".join(lines_at(net, str(params["station"])))
    if kind == "stops_between":
        return str(stations_between(net, str(params["line"]), str(params["from"]), str(params["to"])))
    if kind == "connecting_station":
        x, y = (str(v) for v in params["lines"])  # type: ignore[union-attr]
        return shared_stations(net, x, y)[0]
    if kind == "line_length":
        return str(len(net[str(params["line"])]))
    raise ValueError(f"unknown question kind: {kind}")
