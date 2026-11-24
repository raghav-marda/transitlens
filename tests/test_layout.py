import itertools

import pytest

from conftest import make
from transitlens.layout import LayoutError, LayoutParams, build_map, count_crossings
from transitlens.palette import PALETTES, MIN_COLOUR_DISTANCE, colour_distance


def edges(m):
    for line in m.lines:
        for a, b in zip(line.station_ids, line.station_ids[1:]):
            yield line.name, frozenset((a, b))


@pytest.mark.parametrize("seed", range(25))
def test_map_is_deterministic(seed):
    assert make(seed).network() == make(seed).network()


@pytest.mark.parametrize("seed", range(25))
def test_lines_never_share_a_segment(seed):
    m = make(seed)
    seen = {}
    for name, edge in edges(m):
        assert edge not in seen, f"{name} and {seen[edge]} share a segment"
        seen[edge] = name


@pytest.mark.parametrize("seed", range(25))
def test_network_is_connected(seed):
    m = make(seed)
    net = m.network()
    reached = {next(iter(net))}
    changed = True
    while changed:
        changed = False
        for name, stations in net.items():
            if name not in reached and any(name2 in reached and set(net[name2]) & set(stations) for name2 in net):
                reached.add(name)
                changed = True
    assert reached == set(net)


@pytest.mark.parametrize("seed", range(25))
def test_station_names_are_unique_and_lines_have_no_repeats(seed):
    m = make(seed)
    names = [s.name for s in m.stations.values()]
    assert len(names) == len(set(names))
    for line in m.lines:
        assert len(set(line.station_ids)) == len(line.station_ids)


def test_lines_are_octilinear():
    for seed in range(20):
        m = make(seed)
        for line in m.lines:
            for a, b in zip(line.station_ids, line.station_ids[1:]):
                dx = abs(m.stations[a].gx - m.stations[b].gx)
                dy = abs(m.stations[a].gy - m.stations[b].gy)
                assert max(dx, dy) == 1


def test_want_crossing_is_honoured():
    for seed in range(40):
        try:
            m = build_map(seed, LayoutParams(n_lines=4, want_crossing=True), {})
        except LayoutError:
            continue
        paths = [[(m.stations[s].gx, m.stations[s].gy) for s in line.station_ids] for line in m.lines]
        assert count_crossings(paths) >= 1
        return
    pytest.fail("no layout with a crossing in 40 seeds")


def test_palettes_have_distinguishable_colours():
    for name, palette in PALETTES.items():
        for (a, ca), (b, cb) in itertools.combinations(palette.items(), 2):
            assert colour_distance(ca, cb) >= MIN_COLOUR_DISTANCE, (name, a, b)
