"""Generates a random transit network laid out on an octilinear grid.

Lines run horizontally, vertically or at 45 degrees, the way real schematic maps do. Rules that
keep every map unambiguous and every answer well defined:

* A grid node that two lines share is an interchange station serving both.
* Two lines may also cross without a station, where two diagonals meet in the middle of a grid
  cell. That is a deliberate distractor: the picture shows a crossing, but you cannot change lines.
* Lines never share a segment, and every line is connected to the rest of the network.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .model import Line, Station, TransitMap
from .names import draw_names
from .palette import PALETTES

Node = tuple[int, int]

DIRECTIONS: tuple[Node, ...] = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
_MAX_ATTEMPTS = 400


class LayoutError(RuntimeError):
    """Raised when no valid layout could be produced for the requested parameters."""


@dataclass(frozen=True)
class LayoutParams:
    n_lines: int = 4
    grid_w: int = 13
    grid_h: int = 8
    min_stations: int = 5
    max_stations: int = 8
    palette: str = "classic"
    want_crossing: bool = False  # require at least one station-less crossing
    script: str = "latin"  # script the station names are written in


def _edge(a: Node, b: Node) -> frozenset[Node]:
    return frozenset((a, b))


def _is_diagonal(a: Node, b: Node) -> bool:
    return a[0] != b[0] and a[1] != b[1]


def _anti_diagonal(a: Node, b: Node) -> frozenset[Node]:
    """The other diagonal of the grid cell that the diagonal a-b crosses."""
    return _edge((a[0], b[1]), (b[0], a[1]))


def _rotate(direction: Node, steps: int) -> Node:
    index = DIRECTIONS.index(direction)
    return DIRECTIONS[(index + steps) % len(DIRECTIONS)]


def _walk(
    rng: random.Random,
    start: Node,
    length: int,
    params: LayoutParams,
    occupied: dict[Node, int],
    used_edges: set[frozenset[Node]],
) -> list[Node] | None:
    """Random walk from `start`, preferring to keep heading the same way."""
    path = [start]
    direction = rng.choice(DIRECTIONS)
    previous_hit = False
    while len(path) < length:
        # Weighted shuffle (Efraimidis-Spirakis): keep heading, or bend by 45 degrees either way.
        weighted = ((direction, 0.6), (_rotate(direction, 1), 0.2), (_rotate(direction, -1), 0.2))
        ordered = [
            step for step, weight in sorted(weighted, key=lambda sw: -(rng.random() ** (1 / sw[1])))
        ]
        moved = False
        for step in ordered:
            nxt = (path[-1][0] + step[0], path[-1][1] + step[1])
            if not (0 <= nxt[0] < params.grid_w and 0 <= nxt[1] < params.grid_h):
                continue
            if nxt in path:
                continue
            edge = _edge(path[-1], nxt)
            if edge in used_edges:
                continue
            hit = nxt in occupied
            if hit and previous_hit:
                continue  # never run along another line through two nodes in a row
            path.append(nxt)
            direction = step
            previous_hit = hit
            moved = True
            break
        if not moved:
            return None
    return path


def count_crossings(paths: list[list[Node]]) -> int:
    """Station-less crossings: pairs of lines whose diagonals meet mid-cell."""
    diagonals: dict[frozenset[Node], int] = {}
    for index, path in enumerate(paths):
        for a, b in zip(path, path[1:]):
            if _is_diagonal(a, b):
                diagonals[_edge(a, b)] = index
    count = 0
    for edge, owner in diagonals.items():
        a, b = tuple(edge)
        other = diagonals.get(_anti_diagonal(a, b))
        if other is not None and other != owner:
            count += 1
    return count // 2


def generate_paths(rng: random.Random, params: LayoutParams) -> list[list[Node]]:
    paths: list[list[Node]] = []
    occupied: dict[Node, int] = {}
    used_edges: set[frozenset[Node]] = set()
    attempts = 0
    while len(paths) < params.n_lines:
        attempts += 1
        if attempts > _MAX_ATTEMPTS:
            raise LayoutError("could not place all lines")
        length = rng.randint(params.min_stations, params.max_stations)
        if not paths:
            start = (rng.randint(2, params.grid_w - 3), rng.randint(2, params.grid_h - 3))
        else:
            # Start from a node of an existing line so the network stays connected.
            candidates = [n for n, count in occupied.items() if count == 1] or list(occupied)
            start = rng.choice(sorted(candidates))
        path = _walk(rng, start, length, params, occupied, used_edges)
        if path is None:
            continue
        paths.append(path)
        for node in path:
            occupied[node] = occupied.get(node, 0) + 1
        for a, b in zip(path, path[1:]):
            used_edges.add(_edge(a, b))
    if params.want_crossing and count_crossings(paths) == 0:
        raise LayoutError("no station-less crossing in this layout")
    return paths


def build_map(seed: int, params: LayoutParams, style: dict[str, object]) -> TransitMap:
    """Builds one valid map for `seed`. Deterministic: the same inputs give the same map."""
    rng = random.Random(seed)
    paths = generate_paths(rng, params)

    nodes = sorted({node for path in paths for node in path})
    names = draw_names(rng, len(nodes), params.script)
    node_to_id = {node: f"s{index}" for index, node in enumerate(nodes)}
    stations = {
        node_to_id[node]: Station(node_to_id[node], names[index], node[0], node[1])
        for index, node in enumerate(nodes)
    }

    palette = PALETTES[params.palette]
    colour_names = list(palette)
    rng.shuffle(colour_names)
    lines = tuple(
        Line(
            name=colour_names[i],
            color=palette[colour_names[i]],
            station_ids=tuple(node_to_id[node] for node in path),
        )
        for i, path in enumerate(paths)
    )
    return TransitMap(
        seed=seed,
        grid_w=params.grid_w,
        grid_h=params.grid_h,
        stations=stations,
        lines=lines,
        style={**style, "palette": params.palette, "script": params.script},
    )
