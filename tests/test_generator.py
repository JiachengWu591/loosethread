"""Generator tests: determinism, guarantees on random seeds, speed, and solver soundness."""

import os
import random
import subprocess
import sys
import time

import pytest

from loosethread.audit import audit
from loosethread.generator import (
    AlibiStyle,
    ContradictionRule,
    GenerationError,
    GenParams,
    generate,
)
from loosethread.model import LieReason
from loosethread.solver import Solver

# Property tests draw seeds with stdlib `random` from a fixed meta-seed, so failures reproduce.
SEEDS = random.Random(20261030).sample(range(1_000_000), 40)


def test_same_seed_same_case() -> None:
    assert generate(123).case == generate(123).case


def test_different_seeds_differ() -> None:
    assert generate(1).case != generate(2).case


def test_output_does_not_depend_on_hash_randomization() -> None:
    def run(hash_seed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        result = subprocess.run(
            [sys.executable, "-m", "loosethread.case", "--seed", "5", "--lang", "en"],
            capture_output=True,
            env=env,
            check=True,
        )
        return result.stdout.decode("utf-8")

    assert run("0") == run("12345")


@pytest.mark.parametrize("rule", list(ContradictionRule))
def test_random_seeds_satisfy_all_guarantees(rule: ContradictionRule) -> None:
    params = GenParams(contradiction_rule=rule)
    for seed in SEEDS[:20]:
        case = generate(seed, params).case
        assert audit(case) == [], f"seed {seed}"


def test_true_culprit_survives_any_subset_of_testimony() -> None:
    # Soundness: whatever the player has asked so far, the solver never rules out the culprit.
    rng = random.Random(99)
    for seed in SEEDS[:15]:
        case = generate(seed).case
        solver = Solver(case.view)
        for _ in range(10):
            subset = [i for i in solver.all_statements() if rng.random() < rng.random()]
            assert solver.hypothesis_ok(case.truth.culprit, subset), f"seed {seed}"


def test_every_case_has_an_alibi_lie_and_bounded_privacy_lies() -> None:
    for seed in SEEDS[:20]:
        lies = generate(seed).case.truth.lies
        reasons = [lie.reason for lie in lies]
        assert reasons.count(LieReason.ALIBI) == 1
        assert reasons.count(LieReason.PRIVACY) <= 2
        assert all(lie.exposed_by for lie in lies)


@pytest.mark.parametrize(
    "params",
    [
        GenParams(n_suspects=4, n_slots=6, window=2, n_evidence=4),
        GenParams(n_suspects=6, n_slots=10, window=4, n_evidence=8, optional_locations=True),
        GenParams(alibi_styles=(AlibiStyle.UNREACHABLE,)),
        GenParams(alibi_styles=(AlibiStyle.OCCUPIED, AlibiStyle.UNREACHABLE)),
    ],
)
def test_parameter_extremes_generate_valid_cases(params: GenParams) -> None:
    for seed in SEEDS[:8]:
        case = generate(seed, params).case
        assert audit(case) == [], f"seed {seed}"
        assert len(case.view.suspects) == params.n_suspects
        assert len(case.view.world.slots) == params.n_slots


def test_generation_is_fast() -> None:
    for seed in SEEDS[:20]:
        began = time.perf_counter()
        generate(seed, GenParams(contradiction_rule=ContradictionRule.TRUSTING))
        assert time.perf_counter() - began < 1.0, f"seed {seed}"


def test_invalid_params_are_rejected() -> None:
    with pytest.raises(ValueError, match="n_suspects"):
        GenParams(n_suspects=7)
    with pytest.raises(ValueError, match="window"):
        GenParams(window=5)


def test_impossible_filter_raises() -> None:
    with pytest.raises(GenerationError):
        generate(0, GenParams(min_questions=(40, 50), max_attempts=3))
