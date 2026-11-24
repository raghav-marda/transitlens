"""Plain data model shared by the generator, solvers, renderer and validators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

# A network is the part of a map that questions are about: each line name maps to its
# stations in travel order. Solvers only ever see this, never pixels or coordinates.
Network = Mapping[str, Sequence[str]]


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    gx: int  # grid column
    gy: int  # grid row


@dataclass(frozen=True)
class Line:
    name: str  # colour name, e.g. "Red"; this is how questions refer to the line
    color: str  # hex colour used when drawing
    station_ids: tuple[str, ...]


@dataclass(frozen=True)
class TransitMap:
    seed: int
    grid_w: int
    grid_h: int
    stations: Mapping[str, Station]
    lines: tuple[Line, ...]
    style: Mapping[str, object]

    def network(self) -> dict[str, tuple[str, ...]]:
        """The ground-truth network, keyed by line name, in station-name form."""
        return {
            line.name: tuple(self.stations[sid].name for sid in line.station_ids)
            for line in self.lines
        }

    def interchange_names(self) -> list[str]:
        counts: dict[str, int] = {}
        for line in self.lines:
            for sid in line.station_ids:
                counts[sid] = counts.get(sid, 0) + 1
        return sorted(self.stations[s].name for s, c in counts.items() if c > 1)


def canonical_network(net: Network) -> dict[str, tuple[str, ...]]:
    """Normalises a network so two descriptions of the same map compare equal.

    A line has no inherent direction, so each line is stored in the lexicographically
    smaller of its two orderings.
    """
    out: dict[str, tuple[str, ...]] = {}
    for name, stations in net.items():
        forward = tuple(stations)
        backward = tuple(reversed(forward))
        out[name] = min(forward, backward)
    return out
