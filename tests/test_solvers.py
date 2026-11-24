import itertools
import random

from conftest import make
from transitlens.solve import (
    lines_at, min_interchanges_a, min_interchanges_b, shared_stations, stations_between,
)


def brute_force(net, a, b, closed=()):
    """Third, deliberately naive method: try every ordered set of lines, shortest first."""
    names = [n for n in net if n not in closed]
    for k in range(1, len(names) + 1):
        for route in itertools.permutations(names, k):
            if a not in net[route[0]] or b not in net[route[-1]]:
                continue
            if all(set(net[x]) & set(net[y]) for x, y in zip(route, route[1:])):
                return k - 1
    return None


def test_solvers_agree_with_each_other_and_with_brute_force():
    checked = 0
    for seed in range(40):
        net = make(seed, n_lines=4).network()
        stations = sorted({s for line in net.values() for s in line})
        rng = random.Random(seed)
        for _ in range(15):
            a, b = rng.sample(stations, 2)
            closed = rng.choice([(), (rng.choice(sorted(net)),)])
            fast_a = min_interchanges_a(net, a, b, closed)
            fast_b = min_interchanges_b(net, a, b, closed)
            assert fast_a == fast_b == brute_force(net, a, b, closed), (seed, a, b, closed)
            checked += 1
    assert checked == 600


def test_same_station_costs_nothing_unless_its_lines_are_closed():
    net = {"Red": ("A", "B", "C"), "Blue": ("C", "D")}
    assert min_interchanges_a(net, "A", "A") == 0
    assert min_interchanges_a(net, "A", "A", {"Red"}) is None


def test_hand_checked_example():
    net = {"Red": ("A", "B", "C"), "Blue": ("C", "D", "E"), "Green": ("E", "F")}
    assert min_interchanges_a(net, "A", "F") == 2
    assert min_interchanges_b(net, "A", "F") == 2
    assert min_interchanges_a(net, "A", "F", {"Blue"}) is None
    assert min_interchanges_b(net, "A", "F", {"Blue"}) is None
    assert lines_at(net, "C") == ["Blue", "Red"]
    assert stations_between(net, "Red", "A", "C") == 1
    assert shared_stations(net, "Red", "Blue") == ["C"]
