"""Two independent solvers for 'fewest interchanges', plus helpers for the other question types.

Independence matters: a reference answer is only trustworthy if it is established by more than
one method. Solver A searches a graph of (station, line) states; solver B searches a graph whose
nodes are whole lines. They share no code, and the tests also check both against brute force.
"""

from __future__ import annotations

from collections import deque
from typing import Collection

from .model import Network


def lines_at(net: Network, station: str) -> list[str]:
    return sorted(name for name, stations in net.items() if station in stations)


def min_interchanges_a(
    net: Network, start: str, goal: str, closed: Collection[str] = ()
) -> int | None:
    """0-1 BFS over (station, line) states. Riding costs 0, changing line at a station costs 1."""
    open_lines = {name: stations for name, stations in net.items() if name not in set(closed)}
    if start == goal:
        return 0 if lines_at(open_lines, start) else None
    dist: dict[tuple[str, str], int] = {}
    queue: deque[tuple[str, str]] = deque()
    for line in lines_at(open_lines, start):
        dist[(start, line)] = 0
        queue.append((start, line))
    while queue:
        station, line = queue.popleft()
        here = dist[(station, line)]
        stations = open_lines[line]
        index = stations.index(station)
        for nxt in (index - 1, index + 1):
            if 0 <= nxt < len(stations):
                state = (stations[nxt], line)
                if dist.get(state, 10**9) > here:
                    dist[state] = here
                    queue.appendleft(state)  # cost-0 move goes to the front
        for other in lines_at(open_lines, station):
            if other != line and dist.get((station, other), 10**9) > here + 1:
                dist[(station, other)] = here + 1
                queue.append((station, other))
    best = [d for (station, _), d in dist.items() if station == goal]
    return min(best) if best else None


def min_interchanges_b(
    net: Network, start: str, goal: str, closed: Collection[str] = ()
) -> int | None:
    """BFS over lines: two lines are neighbours if they share a station."""
    open_lines = {name: set(stations) for name, stations in net.items() if name not in set(closed)}
    sources = [name for name, stations in open_lines.items() if start in stations]
    targets = {name for name, stations in open_lines.items() if goal in stations}
    if not sources or not targets:
        return None
    seen = {name: 0 for name in sources}
    queue = deque(sources)
    while queue:
        current = queue.popleft()
        if current in targets:
            return seen[current]
        for other, stations in open_lines.items():
            if other not in seen and open_lines[current] & stations:
                seen[other] = seen[current] + 1
                queue.append(other)
    return None


def stations_between(net: Network, line: str, a: str, b: str) -> int:
    stations = list(net[line])
    return abs(stations.index(a) - stations.index(b)) - 1


def shared_stations(net: Network, line_a: str, line_b: str) -> list[str]:
    return sorted(set(net[line_a]) & set(net[line_b]))
