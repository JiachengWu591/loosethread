"""Simulated systematic player: its first sweep, reproducibility, identification before solving."""

import random

import pytest

from loosethread.game import StarRule
from loosethread.generator import DAILY, generate
from loosethread.model import QueryKind
from loosethread.simulate import question_order, simulate, star_rule, summary


def test_first_sweep_is_every_suspect_over_the_window() -> None:
    case = generate(213, DAILY).case
    view = case.view
    order = question_order(case, random.Random(1))
    sweep = len(view.suspects) * len(view.crime.window)
    assert {(q.addressee, q.slot) for q in order[:sweep]} == {
        (s, t) for s in view.suspects for t in view.crime.window
    }
    assert all(q.kind is QueryKind.WITH_WHOM for q in order[:sweep])
    assert len(order) == len(set(order))


def test_star_rule_is_deterministic_and_capped_at_the_budget() -> None:
    case = generate(0, DAILY).case
    rule = star_rule(case)
    assert rule == star_rule(case)
    assert 0 < rule.three <= rule.two <= 20
    assert star_rule(case, budget=5) == StarRule(5, 5)
    assert (rule.stars(rule.three), rule.stars(rule.three + 1), rule.stars(rule.two + 1)) == (
        3,
        2 if rule.two > rule.three else 1,
        1,
    )


@pytest.mark.parametrize(("three", "two"), [(0, 4), (5, 3)])
def test_star_rule_rejects_impossible_thresholds(three: int, two: int) -> None:
    with pytest.raises(ValueError, match="star thresholds"):
        StarRule(three, two)


def test_runs_are_reproducible_and_identify_before_solving() -> None:
    runs = simulate([0, 213], orders=3)
    assert runs == simulate([0, 213], orders=3)
    for run in runs:
        assert run.solved_at is not None
        assert run.identified_at is not None
        assert run.identified_at <= run.solved_at
    assert summary(runs)[0] == "6 runs: 2 cases x 3 orders; rates are over cases"
