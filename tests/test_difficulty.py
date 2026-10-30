"""Difficulty metric tests."""

import random

from loosethread.difficulty import measure
from loosethread.generator import ContradictionRule, GenParams, generate
from loosethread.solver import Solver

SEEDS = random.Random(424242).sample(range(1_000_000), 12)
TRUSTING = GenParams(contradiction_rule=ContradictionRule.TRUSTING)


def test_question_plan_actually_solves_the_case() -> None:
    for seed in SEEDS:
        case = generate(seed, TRUSTING).case
        metrics = measure(case.view)
        solver = Solver(case.view)
        index = {s: i for i, s in enumerate(solver.statements)}
        claims = [
            c for t in case.view.testimony if t.query in metrics.question_plan for c in t.claims
        ]
        result = solver.consistent({index[c] for c in claims})
        assert result.unique == case.truth.culprit, f"seed {seed}"
        assert len(metrics.question_plan) == metrics.min_questions


def test_trusting_cases_need_a_contradiction() -> None:
    for seed in SEEDS:
        metrics = measure(generate(seed, TRUSTING).case.view)
        assert metrics.trusting_suspects >= 2
        assert metrics.contradictions_required is None or metrics.contradictions_required >= 1
        assert metrics.min_questions >= 2


def test_plan_of_two_or_fewer_is_exact() -> None:
    for seed in SEEDS:
        metrics = measure(generate(seed, TRUSTING).case.view)
        assert metrics.min_questions_exact == (metrics.min_questions <= 2)
