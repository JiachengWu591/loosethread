"""Parser evaluation: the question set's integrity, scoring rules and run guardrails."""

import json
from pathlib import Path

import pytest

from loosethread.generator import DAILY, generate
from loosethread.model import PersonId, Query, QueryKind, SlotIndex
from loosethread.npc import ClarifyReason, ParseRequest, Usage
from loosethread.parser_eval import (
    CHARGED_WRONG,
    CORRECT,
    FROZEN_SHA256,
    INVALID,
    NEEDLESS,
    SET,
    SETTINGS_SET,
    SETTINGS_SHA256,
    Invalid,
    Outcome,
    classify,
    load_items,
    read_rows,
    report,
    run,
    score,
    sha256,
)
from loosethread.stats import mcnemar_exact

ROOT = Path(__file__).resolve().parents[1]
LIN = PersonId("lin")
WHERE_5 = Query(QueryKind.WHERE, LIN, slot=SlotIndex(5))


def test_the_question_set_is_well_formed() -> None:
    items = load_items(ROOT / SET)
    assert len(items) == len({i.id for i in items}) == 199
    assert {i.split for i in items} == {"dev", "test"}
    for item in items:
        world = generate(item.seed, DAILY).case.view.world
        people = {p.id for p in world.people}
        assert item.addressee in people, item.id
        for label in (item.expect, *item.also):
            if isinstance(label, Query):
                assert label.person in people | {None}, item.id
                assert label.location in {x.id for x in world.locations} | {None}, item.id
                assert label.item in {i.id for i in world.items} | {None}, item.id
    if FROZEN_SHA256 is not None:
        assert sha256(ROOT / SET) == FROZEN_SHA256


@pytest.mark.parametrize(
    ("expect", "also", "got", "kind"),
    [
        (WHERE_5, (), WHERE_5, CORRECT),
        (WHERE_5, (), Query(QueryKind.WHERE, LIN, slot=SlotIndex(4)), CHARGED_WRONG),
        (WHERE_5, (), ClarifyReason.NEED_TIME, NEEDLESS),
        (ClarifyReason.ONE_SLOT, (), ClarifyReason.NEED_TIME, CORRECT),  # reasons are pooled
        (ClarifyReason.ONE_SLOT, (), WHERE_5, CHARGED_WRONG),
        (
            Query(QueryKind.OUT_OF_SCOPE, LIN),
            (ClarifyReason.TWO_PEOPLE,),
            ClarifyReason.UNCLEAR,
            CORRECT,
        ),
        (WHERE_5, (), Invalid("not_json"), INVALID),
    ],
)
def test_classify(
    expect: Query | ClarifyReason, also: tuple[Query | ClarifyReason, ...], got: Outcome, kind: str
) -> None:
    assert classify(expect, also, got) == kind


def test_mcnemar_exact() -> None:
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 0) == pytest.approx(2 / 32)
    assert mcnemar_exact(1, 9) == pytest.approx(2 * 11 / 1024)
    assert mcnemar_exact(9, 1) == mcnemar_exact(1, 9)


def _tiny_set(tmp_path: Path) -> Path:
    rows = [
        {"id": "zh001", "split": "dev", "lang": "zh", "seed": 213, "addressee": "lin",
         "question": "你 21:15 在哪？", "expect": {"kind": "where", "slot": 5}, "also": [],
         "tag": "plain"},
        {"id": "zh002", "split": "test", "lang": "zh", "seed": 213, "addressee": "lin",
         "question": "20:15 到 21:00 你都在哪", "expect": {"clarify": "one_slot"}, "also": [],
         "tag": "range"},
        {"id": "en003", "split": "test", "lang": "en", "seed": 213, "addressee": "lin",
         "question": "where were u at 2045", "expect": {"kind": "where", "slot": 3}, "also": [],
         "tag": "en_time_hard"},
    ]  # fmt: skip
    path = tmp_path / "questions.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_rule_run_writes_rows_once(tmp_path: Path) -> None:
    questions = _tiny_set(tmp_path)
    rows_dir = tmp_path / "rows"
    with pytest.raises(SystemExit, match="not frozen"):
        run("rule", "all", None, questions, rows_dir, frozen="0" * 64)
    out = run("rule", "all", None, questions, rows_dir, frozen=sha256(questions))
    rows = read_rows(out)
    assert [r["id"] for r in rows] == ["zh001", "zh002", "en003"]
    result = score(rows, "guarded")
    assert (result.n, result.correct) == (3, 2)  # "2045" is not a clock time to the rules
    assert result.counts.get(NEEDLESS) == 1
    assert "accuracy 2/3" in report(rows, "rule")[0]
    with pytest.raises(SystemExit, match="measured once"):
        run("rule", "all", None, questions, rows_dir, frozen=sha256(questions))


def test_settings_check_is_labelled_as_fixed_and_reads_back_with_rules() -> None:
    assert sha256(ROOT / SETTINGS_SET) == SETTINGS_SHA256
    items = load_items(ROOT / SETTINGS_SET)
    assert {i.pack for i in items} == {"night_ferry", "backstage"}
    rows = read_rows(ROOT / "results/rows/parser-rule-settings-check.jsonl")
    assert score(rows, "guarded").correct == len(items)
    assert all(i.pack == "mistpine" for i in load_items(ROOT / SET))


def test_model_rows_keep_raw_and_guarded_outcomes(tmp_path: Path) -> None:
    questions = _tiny_set(tmp_path)

    def parse(request: ParseRequest) -> tuple[Outcome, Outcome, str | None, Usage]:
        got = Query(QueryKind.WHERE, request.addressee, slot=SlotIndex(3))
        guarded: Outcome = got if "2045" in request.question else ClarifyReason.NEED_TIME
        return got, guarded, '{"kind": "where", "slot": 3}', Usage(1, 900, 12, 0.4)

    out = run("local", "test", None, questions, tmp_path, sha256(questions), parse)
    rows = read_rows(out)
    assert out.name == "parser-local-test.jsonl"
    assert score(rows, "raw").correct == 1
    assert score(rows, "guarded").correct == 2
    lines = report(rows, "local")
    assert any("guard vs raw" in line for line in lines)


def test_deepseek_needs_a_pilot_before_a_full_run(tmp_path: Path) -> None:
    questions = _tiny_set(tmp_path)
    with pytest.raises(SystemExit, match="pilot"):
        run("deepseek", "test", None, questions, tmp_path, sha256(questions))
