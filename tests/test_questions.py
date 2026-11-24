import random

import pytest

from conftest import make
from transitlens.questions import answer_for, generate_questions, q_reroute
from transitlens.solve import min_interchanges_a

KINDS = {"interchange_count", "reroute", "lines_at", "stops_between", "connecting_station", "line_length"}


def test_recomputed_answer_always_equals_reference():
    count = 0
    for seed in range(40):
        net = make(seed).network()
        for q in generate_questions(net, random.Random(seed), 6):
            assert answer_for(q.kind, q.params, net) == q.answer
            count += 1
    assert count > 150


def test_every_kind_is_produced():
    kinds = set()
    for seed in range(20):
        net = make(seed).network()
        kinds |= {q.kind for q in generate_questions(net, random.Random(seed), 6)}
    assert kinds == KINDS


def test_questions_on_one_map_are_distinct():
    net = make(3).network()
    texts = [q.text for q in generate_questions(net, random.Random(0), 6)]
    assert len(texts) == len(set(texts))


def test_reroute_closure_always_changes_the_answer():
    produced = 0
    for seed in range(40):
        net = make(seed).network()
        q = q_reroute(net, random.Random(seed))
        if q is None:
            continue
        produced += 1
        a, b = q.params["from"], q.params["to"]
        assert min_interchanges_a(net, a, b) is not None
        assert q.answer != str(min_interchanges_a(net, a, b))
    assert produced > 20


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        answer_for("nonsense", {}, {})
