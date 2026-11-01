"""Generator tests: determinism, guarantees on random seeds, speed, and solver soundness."""

import hashlib
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator

import pytest

from loosethread.audit import audit
from loosethread.content import load_pack
from loosethread.generator import (
    DAILY,
    PACKS,
    SHAPE_PARAMS,
    AlibiStyle,
    ContradictionRule,
    GenerationError,
    GenParams,
    daily_case,
    daily_setup,
    generate,
)
from loosethread.model import Case, Lie, LieReason, Occupants, PersonAt
from loosethread.solver import Solver

# Property tests draw seeds with stdlib `random` from a fixed meta-seed, so failures reproduce.
SEEDS = random.Random(20261030).sample(range(1_000_000), 40)
CLASSIC_DIGEST = "6b88fe7ccd293ca3588af1f2f5b74e04862a679baeb50b5d839d4cb95cc3e4bb"


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


def _classic_digest(seeds: range) -> str:
    rows = []
    for seed in seeds:
        case = generate(seed, DAILY).case
        rows.append(
            [
                case.truth.culprit,
                [e.text.zh for e in case.view.evidence],
                [f.location for f in case.truth.timeline],
                [(lie.statement.speaker, int(lie.statement.claim.slot)) for lie in case.truth.lies],
            ]
        )
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def test_classic_cases_stay_as_they_were() -> None:
    # Computed from the code before step 4b: the frozen parser set and the P1 numbers rest on it.
    assert _classic_digest(range(10)) == CLASSIC_DIGEST


def _alibi(case: Case) -> Lie:
    (lie,) = [x for x in case.truth.lies if x.reason is LieReason.ALIBI]
    return lie


def _shapes(style: AlibiStyle) -> Iterator[Case]:
    for pack_id in PACKS:
        for seed in SEEDS[:5]:
            yield generate(seed, SHAPE_PARAMS[style], load_pack(pack_id)).case


@pytest.mark.parametrize("pack_id", PACKS)
@pytest.mark.parametrize("style", list(AlibiStyle))
def test_every_shape_in_every_setting_is_sound(pack_id: str, style: AlibiStyle) -> None:
    for seed in SEEDS[:5]:
        case = generate(seed, SHAPE_PARAMS[style], load_pack(pack_id)).case
        assert audit(case) == [], f"seed {seed}"
        assert case.view.pack_id == pack_id
        assert _alibi(case).exposed_by
        solver = Solver(case.view)
        assert solver.consistent().consistent == {case.truth.culprit}, f"seed {seed}"
        rng = random.Random(seed)
        for _ in range(5):  # whatever has been asked, the solver never rules out the culprit
            subset = [i for i in solver.all_statements() if rng.random() < rng.random()]
            assert solver.hypothesis_ok(case.truth.culprit, subset), f"seed {seed}"


def test_the_evidence_shape_places_the_culprit_where_the_claim_cannot_be_reached() -> None:
    for case in _shapes(AlibiStyle.EVIDENCE):
        lie, view = _alibi(case), case.view
        claim = lie.statement.claim
        assert isinstance(claim, PersonAt)
        ids = {x for x in lie.exposed_by if isinstance(x, str)}
        assert ids
        rooms = {x.id: x.neighbors | {x.id} for x in view.world.locations}
        for e in view.evidence:
            if e.id in ids:
                (fact,) = e.establishes
                assert isinstance(fact, PersonAt)
                assert fact.person == case.truth.culprit
                assert abs(fact.slot - claim.slot) == 1
                assert claim.location not in rooms[fact.location]
        near = range(view.crime.window[0] - 1, view.crime.window[-1] + 2)
        placed = {
            f.person
            for e in view.evidence
            for f in e.establishes
            if isinstance(f, PersonAt) and f.slot in near and f.person in view.suspects
        }
        assert len(placed) >= 3  # the culprit is not the only suspect the evidence mentions


def test_the_companion_shape_names_a_suspect_whom_a_third_person_places_elsewhere() -> None:
    for case in _shapes(AlibiStyle.COMPANION):
        lie, truth = _alibi(case), case.truth
        claim = lie.statement.claim
        assert isinstance(claim, Occupants)
        (companion,) = claim.people - {truth.culprit}
        assert companion in case.view.suspects
        where = {(f.person, f.slot): f.location for f in truth.timeline}
        room = where[(companion, claim.slot)]
        assert room != claim.location
        others = {p for (p, t), loc in where.items() if t == claim.slot and loc == room}
        others -= {companion}
        assert others
        assert others <= case.view.suspects
        assert not {p for (p, t), loc in where.items() if t == claim.slot and loc == claim.location}


def test_settings_take_turns_and_shapes_come_up_about_equally() -> None:
    setups = [daily_setup(seed) for seed in range(400)]
    assert [pack.id for pack, _ in setups[:4]] == [*PACKS, PACKS[0]]
    counts = Counter(style for _, style in setups)
    assert set(counts) == set(AlibiStyle)
    assert all(70 <= n <= 130 for n in counts.values())
    assert daily_case(5).case == daily_case(5).case


def test_only_the_older_shapes_share_a_pool() -> None:
    with pytest.raises(ValueError, match="option pool"):
        GenParams(alibi_styles=(AlibiStyle.OCCUPIED, AlibiStyle.COMPANION))


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
