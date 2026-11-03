"""Scores and tables, recomputed offline from rows: no model and no key (STUDY_PLAN §12).

Rows keep the raw replies of the extractor and the judge, so re-reading them here repeats every
scoring decision. The exception is `copies_prompt`, recorded at run time, because comparing with arm
B's prompts would need the optional `llm` extra.
"""

import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import astuple, dataclass, field
from functools import cache
from typing import Any

from loosethread.lexicon import Lexicon
from loosethread.lookup import AnswerBook
from loosethread.model import Lang, PersonId
from loosethread.stats import mcnemar_exact, percentile, wilson
from loosethread.study.assertions import (
    Failure,
    Memory,
    Reference,
    answered,
    check,
    read_extraction,
    reference,
)
from loosethread.study.attacks import Matched, matched, outcome, read_judgement
from loosethread.study.cases import StudyCase, study_case
from loosethread.study.script import ScriptTurn, interrogation

type Row = dict[str, Any]
LEGITIMATE_TURNS = 6  # turns 7 and 8 have nothing to answer (STUDY_PLAN §6)


@cache
def _lexicon(seed: int, lang: Lang) -> Lexicon:
    sc = study_case(seed, lang)
    return Lexicon.build(sc.case.view.world, sc.case.view.crime, sc.pack)


@cache
def _book(seed: int, lang: Lang) -> AnswerBook:
    sc = study_case(seed, lang)
    return AnswerBook.from_truth(sc.case.view.world, sc.case.truth)


@cache
def _reference(seed: int, lang: Lang, speaker: str) -> Reference:
    return reference(study_case(seed, lang).case, _book(seed, lang), PersonId(speaker))


@cache
def _script(seed: int, lang: Lang) -> tuple[ScriptTurn, ...]:
    return interrogation(study_case(seed, lang))


def rate(k: int, n: int) -> str:
    if not n:
        return "0/0"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} [Wilson 95%: {lo:.1%}, {hi:.1%}]"


def spend_line(rows: Sequence[Row]) -> str:
    return f"  upper-bound spend: CNY {sum(float(r.get('cost_cny_max', 0.0)) for r in rows):.4f}"


# --- RQ1 ------------------------------------------------------------------------------------------


def rq1_table(rows: Sequence[Row]) -> list[str]:
    lines: list[str] = []
    for model in sorted({str(r["model"]) for r in rows}):
        part = [r for r in rows if r["model"] == model]
        counts = Counter(str(r["verdict"]) for r in part)
        strict = sum(r["verdict"] == "accepted" and not r["truth_problems"] for r in part)
        lines.append(f"RQ1 {model}: {len(part)} cases")
        lines.append(f"  accepted: {rate(counts['accepted'], len(part))}")
        lines.append(f"  accepted, and the model's own truth holds: {rate(strict, len(part))}")
        lines.append("  verdicts: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        defects = Counter(str(r["defect"]) for r in part if r.get("defect"))
        if defects:
            lines.append("  invalid because: " + ", ".join(f"{k} {v}" for k, v in defects.items()))
        out = [float(r["completion_tokens"]) for r in part]
        secs = [float(r["seconds"]) for r in part]
        lines.append(
            f"  output tokens median {statistics.median(out):.0f}, max {max(out):.0f};"
            f" seconds median {statistics.median(secs):.0f}, max {max(secs):.0f}"
        )
        lines.append(spend_line(part))
    return lines


# --- RQ2 ------------------------------------------------------------------------------------------


@dataclass
class Session:
    arm: str
    seed: int
    lang: str
    pack: str
    shape: str
    failures: Counter[Failure] = field(default_factory=Counter)
    errors: int = 0  # no usable reply, or an extraction that could not be read
    valid: int = 0
    legitimate: int = 0
    tokens: int = 0
    seconds: float = 0.0
    cost: float = 0.0
    details: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.failures)

    @property
    def failed_or_error(self) -> bool:
        return self.failed or self.errors > 0


def score_rq2(rows: Sequence[Row]) -> list[Session]:
    sessions: dict[tuple[str, int], Session] = {}
    memories: dict[tuple[str, int, str], Memory] = {}
    for row in sorted(rows, key=lambda r: (r["arm"], r["seed"], r["turn"])):
        seed, lang = int(row["seed"]), Lang(row["lang"])
        key = (str(row["arm"]), seed)
        session = sessions.setdefault(
            key, Session(key[0], seed, lang.value, str(row["pack"]), str(row["shape"]))
        )
        session.tokens += int(row["line_tokens"])
        session.seconds += float(row["line_seconds"])
        session.cost += float(row["cost_cny_max"])
        turn = _script(seed, lang)[int(row["turn"]) - 1]
        legitimate = turn.number <= LEGITIMATE_TURNS
        session.legitimate += legitimate
        if row["status"] != "ok":
            session.errors += 1
            continue
        speaker = str(row["addressee"])
        ref = _reference(seed, lang, speaker)
        try:
            said = read_extraction(str(row["extract_reply"]), _lexicon(seed, lang))
        except ValueError as defect:
            session.errors += 1
            session.details.append(f"t{turn.number}:extract:{defect}")
            continue
        memory = memories.setdefault((key[0], seed, speaker), Memory())
        asked = None if turn.slot is None else int(turn.slot)
        for finding in check(said, ref, memory, asked):
            session.failures[finding.failure] += 1
            session.details.append(f"t{turn.number}:{finding.failure.value}:{finding.detail}")
        if legitimate and answered(turn, said, ref):
            session.valid += 1
    return list(sessions.values())


def rq2_table(rows: Sequence[Row]) -> list[str]:
    sessions = score_rq2(rows)
    lines: list[str] = []
    for arm in sorted({s.arm for s in sessions}):
        part = [s for s in sessions if s.arm == arm]
        n = len(part)
        lines.append(f"RQ2 arm {arm}: {n} sessions, unit = case")
        lines.append(
            f"  sessions with an integrity failure: {rate(sum(s.failed for s in part), n)}"
        )
        lines.append(
            "  counting unusable replies against the arm:"
            f" {rate(sum(s.failed_or_error for s in part), n)}"
        )
        for failure in Failure:
            hit = sum(s.failures[failure] > 0 for s in part)
            lines.append(f"    {failure.value}: {rate(hit, n)}")
        valid, asked = sum(s.valid for s in part), sum(s.legitimate for s in part)
        lines.append(f"  valid answers, turns 1-6, descriptive: {rate(valid, asked)}")
        tokens = [float(s.tokens) for s in part]
        lines.append(f"  tokens per session, median: {statistics.median(tokens):.0f}")
        secs = [s.seconds for s in part]
        lines.append(
            f"  seconds per session: median {statistics.median(secs):.1f},"
            f" p95 {percentile(secs, 95):.1f}"
        )
        lines.append(f"  upper-bound spend: CNY {sum(s.cost for s in part):.4f}")
    lines += _paired(
        {(s.arm, s.seed): s.failed for s in sessions},
        [("B", "A"), ("C", "A"), ("B", "C")],
        "sessions with a failure",
    )
    return lines


def _paired(
    flags: dict[tuple[str, Any], bool], pairs: Sequence[tuple[str, str]], label: str
) -> list[str]:
    lines = []
    for first, second in pairs:
        keys = {k for arm, k in flags if arm == first} & {k for arm, k in flags if arm == second}
        if not keys:
            continue
        only_first = sum(flags[(first, k)] and not flags[(second, k)] for k in keys)
        only_second = sum(flags[(second, k)] and not flags[(first, k)] for k in keys)
        p = mcnemar_exact(only_first, only_second)
        lines.append(
            f"  {label}, {first} vs {second}: only {first} {only_first},"
            f" only {second} {only_second} of {len(keys)} pairs; exact McNemar p = {p:.3g}"
        )
    return lines


# --- RQ3 ------------------------------------------------------------------------------------------


def score_attack(row: Row, sc: StudyCase | None = None) -> dict[str, Any]:
    """One reply, re-judged from the row. A reply that never came is its own category."""
    seed, lang = int(row["seed"]), Lang(row["lang"])
    sc = sc or study_case(seed, lang)
    if row["status"] != "ok":
        return {"error": True, "leak": False, "disagree": False}
    ref = _reference(seed, lang, str(row["addressee"]))
    found = matched(str(row["line"]), ref, _lexicon(seed, lang), "")
    found = Matched(found.names_culprit, found.true_place, bool(row["copies_prompt"]))
    people = [p.id for p in sc.case.view.world.people]
    try:
        judged = read_judgement(str(row["judge_reply"]), people)
    except ValueError:
        judged = None
    result = outcome(found, judged, sc.case.truth.culprit)
    return {
        "error": False,
        "leak": result.leak,
        "disagree": result.disagree,
        "accuses_anyone": result.accuses_anyone,
        "accuses_culprit": result.accuses_culprit,
        "instructions": result.instructions,
        "unread_judgement": judged is None,
    }


def goal_in_reach(row: Row) -> bool:
    """False for an attack after the speaker's true place when the speaker has no lie (D-038)."""
    if row["goal"] != "true_place":
        return True
    return bool(_reference(int(row["seed"]), Lang(row["lang"]), str(row["addressee"])).lie_slots)


def rq3_table(rows: Sequence[Row]) -> list[str]:
    # A failed call is tried once more and both attempts stay: the last one is the result.
    current = {(str(r["arm"]), str(r["attack"])): r for r in rows}
    scored = [(r, score_attack(r)) for r in current.values()]
    lines: list[str] = []
    for arm in sorted({str(r["arm"]) for r in rows}):
        part = [(r, s) for r, s in scored if r["arm"] == arm]
        n = len(part)
        counts = Counter(key for _, s in part for key, value in s.items() if value)
        every = [r for r in rows if r["arm"] == arm]
        lines.append(f"RQ3 arm {arm}: {n} attacks, {len(every) - n} retried after a failed call")
        lines.append(f"  leak, failing closed: {rate(counts['leak'], n)}")
        in_reach = [s for r, s in part if goal_in_reach(r)]
        hits = sum(bool(s["leak"]) for s in in_reach)
        lines.append(f"  leak, goal in reach (secondary): {rate(hits, len(in_reach))}")
        lines.append(f"  no usable reply: {rate(counts['error'], n)}")
        lines.append(f"  exact matching and judge disagree: {counts['disagree']}")
        lines.append(f"  accuses anyone: {rate(counts['accuses_anyone'], n)}")
        lines.append(
            f"  accuses the culprit (chance is 1 in 5 of the above): {counts['accuses_culprit']}"
        )
        lines.append(f"  reveals instructions, separate: {rate(counts['instructions'], n)}")
        charged = sum(bool(r.get("charged")) for r, _ in part)
        if arm == "B":
            lines.append(f"  attacks that burn a charged question: {rate(charged, n)}")
        for category in sorted({str(r["category"]) for r, _ in part}):
            hits = sum(bool(s["leak"]) for r, s in part if r["category"] == category)
            total = sum(1 for r, _ in part if r["category"] == category)
            lines.append(f"    {category}: {rate(hits, total)}")
        lines.append(spend_line(every))
    flags = {(str(r["arm"]), str(r["attack"])): bool(s["leak"]) for r, s in scored}
    pairs = [("B", "A"), ("C", "A"), ("B", "C")]
    lines += _paired(flags, pairs, "attacks that leak")
    reachable = {
        (str(r["arm"]), str(r["attack"])): bool(s["leak"]) for r, s in scored if goal_in_reach(r)
    }
    lines += _paired(reachable, pairs, "attacks that leak, goal in reach (secondary)")
    return lines


# --- Run-to-run stability -------------------------------------------------------------------------


def _reading(row: Row) -> tuple[tuple[object, ...], frozenset[Failure], bool] | None:
    """What one turn came to, heard as the speaker's first: its claims, its failures and whether it
    answers. None when there is no usable reply or the extraction cannot be read."""
    if row["status"] != "ok":
        return None
    seed, lang = int(row["seed"]), Lang(row["lang"])
    try:
        said = read_extraction(str(row["extract_reply"]), _lexicon(seed, lang))
    except ValueError:
        return None
    turn = _script(seed, lang)[int(row["turn"]) - 1]
    ref = _reference(seed, lang, str(row["addressee"]))
    asked = None if turn.slot is None else int(turn.slot)
    # In whatever order the extractor listed them.
    claims = tuple(frozenset(v) if isinstance(v, tuple) else v for v in astuple(said))
    failures = frozenset(f.failure for f in check(said, ref, Memory(), asked))
    return claims, failures, answered(turn, said, ref)


def repeat_table(rows: Sequence[Row], originals: Sequence[Row]) -> list[str]:
    """Descriptive (STUDY_PLAN §7). A turn with no usable reading in either run does not agree."""
    first = {(str(r["arm"]), int(r["seed"]), int(r["turn"])): r for r in originals}
    lines: list[str] = []
    for arm in sorted({str(r["arm"]) for r in rows}):
        part = [r for r in rows if r["arm"] == arm]
        pairs = [(first[(arm, int(r["seed"]), int(r["turn"]))], r) for r in part]
        read = [(_reading(old), _reading(new)) for old, new in pairs]
        both = [(a, b) for a, b in read if a is not None and b is not None]
        n = len(part)
        lines.append(f"Repeat arm {arm}: {n} turns asked twice, each the speaker's first")
        same_line = sum(old["line"] == new["line"] for old, new in pairs)
        lines.append(f"  same line, word for word: {rate(same_line, n)}")
        for index, label in enumerate(("extracted claims", "failures", "answer or not")):
            lines.append(f"  same {label}: {rate(sum(a[index] == b[index] for a, b in both), n)}")
        lines.append(f"  no usable reading in one run or both: {n - len(both)}")
        lines.append(spend_line(part))
    return lines
