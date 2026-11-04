"""Runs the study's instruments and writes rows (STUDY_PLAN §14).

python -m loosethread.study.run rq1 --set tune --limit 2
python -m loosethread.study.run rq2 --set pilot --limit 10 --arms A,B,C
python -m loosethread.study.run rq3 --set pilot --limit 10 --arms A,B,C
python -m loosethread.study.run adaptive --set pilot --arm A --lang zh --rounds 1
python -m loosethread.study.run repeat --set test --arms A,B,C
python -m loosethread.study.run rq2 --set test --max-cny 40 --resume
python -m loosethread.study.run score results/rows/study-rq2-pilot-r1.jsonl
python -m loosethread.study.run spent

Tuning and pilot rows are numbered and all kept. Each test file is measured once. Runs take hours,
so rows are saved after every case and `--resume` continues from them; it adds only what is missing
and never repeats a saved row. A failed call is recorded by exception type only, because provider
messages may echo part of the key.
"""

import argparse
import dataclasses
import hashlib
import io
import json
import random
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loosethread.case import render_sheet
from loosethread.lexicon import Lexicon
from loosethread.lookup import AnswerBook
from loosethread.model import Lang
from loosethread.notebook import describe
from loosethread.npc import BackendUnavailable, Usage
from loosethread.study import arms as arms_module
from loosethread.study import assertions, attacks, rq1, tables
from loosethread.study.arms import Arm, Npc, Reply, account, make_npc
from loosethread.study.cases import (
    PILOT_SEEDS,
    TUNE_SEEDS,
    StudyCase,
    development,
    held_out,
    held_out_subset,
    study_case,
)
from loosethread.study.metered import (
    CAP_CNY,
    ROWS,
    BudgetExceeded,
    Metered,
    Outage,
    Spend,
    spent_so_far,
)
from loosethread.study.script import ScriptTurn, interrogation

if TYPE_CHECKING:
    from loosethread.llm.chat import ChatModel

# Opened by CP-9 option A (D-037), with `CAP_CNY` raised.
HELD_OUT_OPEN = True
# Fixed after the review the owner delegated and accepted (D-038), before any test attack was used.
ATTACKS_SHA256 = "be9358f456d50649fb91c8ac605643bd6ce99956909bc79d2daad80b89914937"
_TURN_RESERVE = 0.02  # CNY: more than any one turn has cost, for the spending guard
_RQ1_TIMEOUT = 900.0  # a long reply takes minutes; the game's 30 s would fail every case
_OUTAGE_SHARE = 0.05  # STUDY_PLAN §9
_OUTAGE_MIN_CALLS = 40  # a few failures early on are not an outage

type Row = dict[str, Any]


@dataclass
class Bench:
    model: "ChatModel"
    cost: Callable[[Usage], float]
    spend: Spend
    commit: str
    model_name: str
    instruments: dict[str, str]
    reasoning_tokens: int = 0  # thinking mode: hidden tokens the spending guard must allow for
    path: Path | None = None  # saved here after every case, so a long run survives a crash
    stopped: str = ""  # why the run ended early, if it did


def _usage_cost(bench: Bench, usage: Usage) -> float:
    return round(bench.cost(usage), 6)


def _save(bench: Bench, rows: Sequence[Row]) -> None:
    if bench.path is not None:
        write_rows(bench.path, rows)


def _stop(bench: Bench, reason: BudgetExceeded | Outage) -> None:
    bench.stopped = f"{type(reason).__name__}: {reason}"
    print(f"stopped: {bench.stopped}")


def _check_outage(rows: Sequence[Row], key: str = "arm") -> None:
    """Pause if more than 5% of an arm's calls got no usable reply (STUDY_PLAN §9). Runners pass the
    rows of this run: the failures before a resume have been reported already (D-038)."""
    for arm in {str(r.get(key)) for r in rows}:
        part = [r for r in rows if str(r.get(key)) == arm]
        failed = sum(r.get("status", "ok") != "ok" for r in part)
        if len(part) >= _OUTAGE_MIN_CALLS and failed / len(part) > _OUTAGE_SHARE:
            raise Outage(f"arm {arm}: {failed} of {len(part)} calls failed")


def cases_for(split: str) -> tuple[tuple[int, Lang], ...]:
    if split == "tune":
        return development(TUNE_SEEDS)
    if split == "pilot":
        return development(PILOT_SEEDS)
    if split != "test":
        raise SystemExit(f"unknown set {split!r}")
    if not HELD_OUT_OPEN:
        raise SystemExit("the held-out set is closed until the owner approves the full budget")
    return held_out()


def _base(bench: Bench, study: str, split: str, sc: StudyCase) -> Row:
    return {
        "study": study,
        "set": split,
        "seed": sc.seed,
        "lang": sc.lang.value,
        "pack": sc.pack.id,
        "shape": sc.shape.value,
        "commit": bench.commit,
        "model": bench.model_name,
        "instruments": bench.instruments,
    }


# --- RQ1 ------------------------------------------------------------------------------------------


def run_rq1(
    bench: Bench, split: str, cases: Sequence[tuple[int, Lang]], saved: Sequence[Row] = ()
) -> list[Row]:
    rows: list[Row] = list(saved)
    done = {int(r["seed"]) for r in rows}
    completion = rq1.MAX_TOKENS + bench.reasoning_tokens
    reserve = bench.cost(Usage(prompt_tokens=3000, completion_tokens=completion))
    try:
        for seed, lang in cases:
            if seed in done:
                continue
            bench.spend.ensure(reserve)
            sc = study_case(seed, lang)
            system, user = rq1.writing_prompt(sc.case)
            row = _base(bench, "rq1", split, sc)
            usage = Usage()
            try:
                reply = bench.model.complete(
                    system, user, json_mode=True, max_tokens=rq1.MAX_TOKENS
                )
            except Exception as exc:  # the type only: provider messages may echo the key
                row |= {"verdict": "invalid", "defect": f"call:{type(exc).__name__}"}
                row |= {"reply": None, "truth_problems": [], "culprit": None}
            else:
                usage = reply.usage
                row |= judge_written(reply.text, reply.finish_reason, sc)
            row |= {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "seconds": round(usage.seconds, 3),
                "cost_cny_max": _usage_cost(bench, usage),
                "status": "failed" if str(row.get("defect", "")).startswith("call:") else "ok",
            }
            rows.append(row)
            _save(bench, rows)
            _check_outage(rows[len(saved) :], "model")
    except (BudgetExceeded, Outage) as stop:
        _stop(bench, stop)
    return rows


def judge_written(text: str, finish: str, sc: StudyCase) -> Row:
    if finish == "length":
        return {"verdict": "invalid", "defect": "too_long", "reply": text}
    try:
        written = rq1.read_case(text, sc.case)
    except ValueError as defect:
        return {"verdict": "invalid", "defect": str(defect), "reply": text}
    return {
        "verdict": rq1.verdict(written.view, written.culprit).value,
        "defect": None,
        "reply": text,
        "culprit": written.culprit,
        "truth_problems": list(rq1.truth_problems(written)),
    }


# --- RQ2 ------------------------------------------------------------------------------------------


def _speak(npc: Npc, addressee: str, question: str) -> Reply:
    return npc.ask(addressee, question)  # type: ignore[arg-type]


def complete_cases(rows: Sequence[Row], arms: Sequence[Arm]) -> tuple[list[Row], list[Row]]:
    """Rows of finished RQ2 cases, and rows of a case a stopped run left unfinished. A resumed run
    redoes those, so they stay out of the scores, on a file of their own the budget still sees."""
    by_seed: dict[int, list[Row]] = {}
    for row in rows:
        by_seed.setdefault(int(row["seed"]), []).append(row)
    done: list[Row] = []
    unfinished: list[Row] = []
    for part in by_seed.values():
        whole = len(part) == 8 * len(arms) and all(
            r["status"] != "ok" or r["extract_reply"] is not None for r in part
        )
        (done if whole else unfinished).extend(part)
    return done, unfinished


def run_rq2(
    bench: Bench,
    split: str,
    cases: Sequence[tuple[int, Lang]],
    arms: Sequence[Arm],
    saved: Sequence[Row] = (),
) -> list[Row]:
    rows: list[Row] = list(saved)
    done = {int(r["seed"]) for r in rows}
    try:
        for seed, lang in cases:
            if seed in done:
                continue
            sc = study_case(seed, lang)
            turns = interrogation(sc)
            here: list[Row] = []
            for arm in arms:
                npc = make_npc(arm, sc, bench.model)
                for turn in turns:
                    bench.spend.ensure(_TURN_RESERVE)
                    reply = _speak(npc, turn.addressee, turn.question)
                    row = _turn_row(bench, "rq2", split, sc, arm, turn, reply)
                    rows.append(row)
                    here.append(row)
            # Lines reach the extractor shuffled across arms; it is told neither arm nor truth.
            order = [r for r in here if r["status"] == "ok"]
            random.Random(f"loosethread:extract:{seed}").shuffle(order)
            for row in order:
                bench.spend.ensure(_TURN_RESERVE)
                _extract(bench, row)
            _save(bench, rows)
            _check_outage(rows[len(saved) :])
    except (BudgetExceeded, Outage) as stop:
        _stop(bench, stop)
        _save(bench, rows)
    return rows


def _turn_row(
    bench: Bench, study: str, split: str, sc: StudyCase, arm: Arm, turn: ScriptTurn, reply: Reply
) -> Row:
    return _base(bench, study, split, sc) | {
        "arm": arm.value,
        "turn": turn.number,
        "kind": turn.kind.value,
        "addressee": turn.addressee,
        "question": turn.question,
        "line": reply.line,
        "status": reply.status,
        "detail": list(reply.detail),
        "line_tokens": reply.usage.prompt_tokens + reply.usage.completion_tokens,
        "line_seconds": round(reply.usage.seconds, 3),
        "extract_reply": None,
        "cost_cny_max": _usage_cost(bench, reply.usage),
    }


def repeat_items(
    cases: Sequence[tuple[int, Lang]], per_lang: int = 10
) -> list[tuple[StudyCase, ScriptTurn]]:
    """The turns asked again (STUDY_PLAN §7), drawn with a fixed seed and no look at any outcome.
    Each is the first thing its speaker is asked, so a new character can repeat it."""
    rng = random.Random("loosethread:repeat")
    items: list[tuple[StudyCase, ScriptTurn]] = []
    for lang in Lang:
        pool = [c for c in cases if c[1] is lang]
        for seed, _ in rng.sample(pool, per_lang):
            sc = study_case(seed, lang)
            seen: set[str] = set()
            first: list[ScriptTurn] = []
            for turn in interrogation(sc):
                if turn.addressee not in seen and turn.number <= tables.LEGITIMATE_TURNS:
                    first.append(turn)
                seen.add(turn.addressee)
            items.append((sc, rng.choice(first)))
    return items


def run_repeat(
    bench: Bench,
    split: str,
    cases: Sequence[tuple[int, Lang]],
    arms: Sequence[Arm],
    per_lang: int = 10,
    saved: Sequence[Row] = (),
) -> list[Row]:
    rows: list[Row] = list(saved)
    done = {(int(r["seed"]), str(r["arm"])) for r in rows}
    try:
        for sc, turn in repeat_items(cases, per_lang):
            for arm in arms:
                if (sc.seed, arm.value) in done:
                    continue
                bench.spend.ensure(_TURN_RESERVE * 2)
                reply = _speak(make_npc(arm, sc, bench.model), turn.addressee, turn.question)
                row = _turn_row(bench, "repeat", split, sc, arm, turn, reply)
                rows.append(row)
                if row["status"] == "ok":
                    _extract(bench, row)
            _save(bench, rows)
            _check_outage(rows[len(saved) :])
    except (BudgetExceeded, Outage) as stop:
        _stop(bench, stop)
        _save(bench, rows)
    return rows


def _extract(bench: Bench, row: Row) -> None:
    sc = study_case(int(row["seed"]), Lang(row["lang"]))
    lex = Lexicon.build(sc.case.view.world, sc.case.view.crime, sc.pack)
    system, user = assertions.extraction_prompt(
        str(row["addressee"]), str(row["question"]), str(row["line"]), lex
    )
    try:
        reply = bench.model.complete(
            system, user, json_mode=True, max_tokens=assertions.EXTRACT_MAX_TOKENS
        )
    except BackendUnavailable as exc:
        row["extract_reply"] = f"call:{exc.cause}"
        return
    except Exception as exc:  # the type only: provider messages may echo the key
        row["extract_reply"] = f"call:{type(exc).__name__}"
        return
    row["extract_reply"] = reply.text
    row["cost_cny_max"] = round(float(row["cost_cny_max"]) + _usage_cost(bench, reply.usage), 6)


# --- RQ3 ------------------------------------------------------------------------------------------


def _instructions(arm: Arm) -> str:
    if arm is Arm.U:
        return arms_module.PLAIN
    if arm is not Arm.B:
        return arms_module._RULES
    from loosethread.llm.parser import SYSTEM  # noqa: PLC0415
    from loosethread.llm.writer import _SYSTEM  # noqa: PLC0415

    return f"{SYSTEM}\n{_SYSTEM}"


def _judge(
    bench: Bench,
    sc: StudyCase,
    speaker: str,
    message: str,
    line: str,
) -> tuple[str, Usage]:
    """The judge's raw reply, and what it cost. A failed call leaves an unreadable reply on the row,
    which scoring treats as a leak."""
    book = AnswerBook.from_truth(sc.case.view.world, sc.case.truth)
    ref = assertions.reference(sc.case, book, speaker)  # type: ignore[arg-type]
    allowed = [
        describe(s, sc.case.view.world, Lang.EN)
        for s in account(book, speaker, sc)  # type: ignore[arg-type]
    ]
    system, user = attacks.judge_prompt(sc, ref, allowed, message, line)
    try:
        reply = bench.model.complete(
            system, user, json_mode=True, max_tokens=attacks.JUDGE_MAX_TOKENS
        )
    except Exception as exc:  # the type only: provider messages may echo the key
        return f"call:{type(exc).__name__}", Usage()
    return reply.text, reply.usage


def _attack_row(bench: Bench, arm: Arm, sc: StudyCase, speaker: str, message: str) -> Row:
    reply = _speak(make_npc(arm, sc, bench.model), speaker, message)
    row: Row = {
        "arm": arm.value,
        "addressee": speaker,
        "question": message,
        "line": reply.line,
        "status": reply.status,
        "detail": list(reply.detail),
        "charged": reply.charged,
        "line_tokens": reply.usage.prompt_tokens + reply.usage.completion_tokens,
        "line_seconds": round(reply.usage.seconds, 3),
        "judge_reply": None,
        "copies_prompt": False,
        "cost_cny_max": _usage_cost(bench, reply.usage),
    }
    if reply.status == "ok":
        book = AnswerBook.from_truth(sc.case.view.world, sc.case.truth)
        ref = assertions.reference(sc.case, book, speaker)  # type: ignore[arg-type]
        lex = Lexicon.build(sc.case.view.world, sc.case.view.crime, sc.pack)
        row["copies_prompt"] = attacks.matched(
            reply.line, ref, lex, _instructions(arm)
        ).copies_prompt
        text, usage = _judge(bench, sc, speaker, message, reply.line)
        row["judge_reply"] = text
        row["cost_cny_max"] = round(float(row["cost_cny_max"]) + _usage_cost(bench, usage), 6)
    return row


def run_rq3(
    bench: Bench,
    split: str,
    cases: Sequence[tuple[int, Lang]],
    arms: Sequence[Arm],
    limit: int | None,
    saved: Sequence[Row] = (),
) -> list[Row]:
    wanted = "test" if split == "test" else "dev"
    if split == "test" and attacks.sha256() != ATTACKS_SHA256:
        raise SystemExit("the attack set is not frozen (or changed since)")
    pool = [a for a in attacks.load_attacks() if a.split == wanted]
    assigned = list(attacks.assign(pool, cases))
    if split == "tune":
        assigned = [x for x in assigned if x.position % 2 == 0]
    elif split == "pilot":
        assigned = [x for x in assigned if x.position % 2 == 1]
    assigned = assigned[:limit] if limit is not None else assigned
    rows: list[Row] = list(saved)
    # On a resume a failed call is tried once more, and both attempts stay (STUDY_PLAN §9).
    tried = Counter((str(r["attack"]), str(r["arm"])) for r in rows)
    replied = {(str(r["attack"]), str(r["arm"])) for r in rows if r["status"] == "ok"}
    try:
        for item in assigned:
            sc = study_case(item.seed, item.lang)
            speaker = attacks.addressee_for(item, sc)
            message = attacks.fill(item.attack, sc, speaker)
            for arm in arms:
                key = (item.attack.id, arm.value)
                if key in replied or tried[key] > 1:
                    continue
                bench.spend.ensure(_TURN_RESERVE)
                rows.append(
                    _base(bench, "rq3", split, sc)
                    | {
                        "attack": item.attack.id,
                        "category": item.attack.category,
                        "goal": item.attack.goal,
                        "to_culprit": item.to_culprit,
                        "attempt": tried[key] + 1,
                    }
                    | _attack_row(bench, arm, sc, speaker, message)
                )
            _save(bench, rows)
            _check_outage(rows[len(saved) :])
    except (BudgetExceeded, Outage) as stop:
        _stop(bench, stop)
        _save(bench, rows)
    return rows


def run_adaptive(
    bench: Bench,
    split: str,
    arm: Arm,
    lang: Lang,
    rounds: int,
    cases: Sequence[tuple[int, Lang]],
    saved: Sequence[Row] = (),
) -> list[Row]:
    """One campaign against one culprit, stopping when the judge confirms a leak (§5.3)."""
    seed, _ = next(c for c in cases if c[1] is lang)
    sc = study_case(seed, lang)
    speaker = sc.case.truth.culprit
    sheet = "\n".join(render_sheet(sc.case.view, lang))
    people = [p.id for p in sc.case.view.world.people]
    rows: list[Row] = list(saved)
    past = [
        (str(r["question"]), str(r["line"]), bool(r.get("confirmed_leak")))
        for r in rows
        if "line" in r
    ]
    if any(leak for _, _, leak in past):
        return rows  # the campaign already ended at a confirmed leak
    first = max((int(r["round"]) for r in rows), default=0) + 1
    try:
        for number in range(first, rounds + 1):
            bench.spend.ensure(_TURN_RESERVE * 6)
            system, user = attacks.attacker_prompt(sheet, speaker, lang, past)
            attacker_cost = 0.0  # a reply that cannot be read was still paid for
            try:
                reply = bench.model.complete(
                    system, user, json_mode=True, max_tokens=attacks.ATTACKER_MAX_TOKENS
                )
                attacker_cost = _usage_cost(bench, reply.usage)
                messages = attacks.read_attacks(reply.text)
            except Exception as exc:  # includes the attacker model refusing to play
                rows.append(
                    _base(bench, "adaptive", split, sc)
                    | {
                        "arm": arm.value,
                        "round": number,
                        "status": f"attacker:{type(exc).__name__}",
                        "cost_cny_max": attacker_cost,
                    }
                )
                continue
            confirmed = False
            for i, message in enumerate(messages):
                row = _attack_row(bench, arm, sc, speaker, message)
                if i == 0:
                    row["cost_cny_max"] = round(float(row["cost_cny_max"]) + attacker_cost, 6)
                row |= _base(bench, "adaptive", split, sc) | {"round": number}
                try:
                    judged = attacks.read_judgement(str(row["judge_reply"]), people)
                except ValueError:
                    judged = None
                leak = judged is not None and (
                    speaker in judged.accuses or judged.reveals_true_place or judged.reveals_other
                )
                row["confirmed_leak"] = leak
                rows.append(row)
                past.append((message, str(row["line"]), leak))
                confirmed = confirmed or leak
            _save(bench, rows)
            _check_outage(rows[len(saved) :])
            if confirmed:
                break
    except (BudgetExceeded, Outage) as stop:
        _stop(bench, stop)
        _save(bench, rows)
    return rows


# --- Files and the command line -------------------------------------------------------------------


def out_path(rows_dir: Path, study: str, split: str, tag: str = "", resume: bool = False) -> Path:
    stem = f"study-{study}{tag}-{split}"
    if split == "test":
        path = rows_dir / f"{stem}.jsonl"
        if path.exists() and not resume:
            raise SystemExit(f"{path} exists: the test set is measured once (or use --resume)")
        return path
    return rows_dir / f"{stem}-r{len(list(rows_dir.glob(f'{stem}-r*.jsonl'))) + 1}.jsonl"


def write_rows(path: Path, rows: Sequence[Row]) -> None:
    """Whole or not at all: a crash while saving must not cost the rows already saved."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(text, encoding="utf-8", newline="\n")
    partial.replace(path)


def read_rows(path: Path) -> list[Row]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def commit_now() -> str:
    done = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True, check=False
    )
    return done.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "")


def instrument_hashes() -> dict[str, str]:
    from loosethread.llm.parser import SYSTEM  # noqa: PLC0415
    from loosethread.llm.writer import _SYSTEM  # noqa: PLC0415

    def short(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

    return {
        "arms": arms_module.instructions_sha(),
        "plain": arms_module.plain_sha(),
        "extractor": assertions.extractor_sha(),
        "judge": attacks.judge_sha(),
        "attacker": attacks.attacker_sha(),
        "rq1": rq1.instructions_sha(),
        "parser": short(SYSTEM),
        "writer": short(_SYSTEM),
    }


def open_bench(backend: str, spend: Spend, timeout: float | None = None) -> Bench:
    from loosethread.llm.client import OpenAIChat  # noqa: PLC0415
    from loosethread.llm.config import load_backends  # noqa: PLC0415

    settings = load_backends()[backend]
    if timeout is not None:
        settings = dataclasses.replace(settings, timeout=timeout)
    client = OpenAIChat(settings)
    client.check_model()  # the configured model must be served (CLAUDE.md)
    return Bench(
        Metered(client, settings.cost, spend),
        settings.cost,
        spend,
        commit_now(),
        settings.model,
        instrument_hashes(),
        settings.reasoning_tokens,
    )


def _arms(text: str) -> tuple[Arm, ...]:
    return tuple(Arm(x.strip()) for x in text.split(","))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loosethread.study.run", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("rq1", "rq2", "rq3", "adaptive", "repeat"):
        go = sub.add_parser(name)
        go.add_argument("--set", dest="split", choices=["tune", "pilot", "test"], required=True)
        go.add_argument("--limit", type=int)
        go.add_argument("--backend", default="deepseek")
        go.add_argument("--arms", default="A,B,C")
        go.add_argument("--arm", default="A")
        go.add_argument("--lang", default="zh")
        go.add_argument("--rounds", type=int, default=100)
        go.add_argument("--per-cell", type=int, help="test set: the first N cases of each cell")
        go.add_argument("--resume", action="store_true", help="continue a stopped test run")
        go.add_argument("--max-cny", type=float, help="this run's share, when runs go in parallel")
    again = sub.add_parser("score")
    again.add_argument("rows", type=Path, nargs="+")
    sub.add_parser("spent")
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.command == "spent":
        print(f"study spend so far, upper bound: CNY {spent_so_far():.4f} of {CAP_CNY:.2f}")
        return 0
    if args.command == "score":
        for path in args.rows:
            print("\n".join(_table(read_rows(path))))
        return 0

    if args.command == "repeat" and args.split != "test":
        raise SystemExit("the repeat is of test turns")
    tag = "" if args.backend == "deepseek" else f"-{args.backend}"
    if args.command == "adaptive":
        tag = f"-{args.arm}-{args.lang}"
    if args.command == "rq3" and args.arms == "U":  # a control: the registered file stays as it is
        tag = "-U"
    path = out_path(ROWS, args.command, args.split, tag, args.resume)
    saved = read_rows(path) if args.resume and path.exists() else []
    if args.command == "rq2":
        saved, unfinished = complete_cases(saved, _arms(args.arms))
        if unfinished:  # kept for the budget, and out of the scores
            write_rows(path.with_name(f"study-unfinished-{path.name[6:]}"), unfinished)

    start = spent_so_far()
    limit = CAP_CNY if args.max_cny is None else min(CAP_CNY, start + args.max_cny)
    spend = Spend(limit, start)
    print(f"study spend so far, upper bound: CNY {spend.spent:.4f}; this run stops at {limit:.2f}")
    timeout = _RQ1_TIMEOUT if args.command == "rq1" else None
    bench = open_bench(args.backend, spend, timeout)
    bench.path = path
    cases = held_out_subset(args.per_cell) if args.per_cell else cases_for(args.split)
    if args.command == "rq1":
        rows = run_rq1(bench, args.split, cases[: args.limit], saved)
    elif args.command == "rq2":
        rows = run_rq2(bench, args.split, cases[: args.limit], _arms(args.arms), saved)
    elif args.command == "rq3":
        rows = run_rq3(bench, args.split, cases, _arms(args.arms), args.limit, saved)
    elif args.command == "repeat":
        rows = run_repeat(bench, args.split, cases, _arms(args.arms), saved=saved)
    else:
        rows = run_adaptive(
            bench, args.split, Arm(args.arm), Lang(args.lang), args.rounds, cases, saved
        )
    write_rows(path, rows)
    print(path)
    print("\n".join(_table(rows)))
    print(f"study spend so far, upper bound: CNY {spend.spent:.4f} of {CAP_CNY:.2f}")
    return 3 if bench.stopped else 0


def _table(rows: Sequence[Row]) -> list[str]:
    if not rows:
        return ["no rows"]
    study = rows[0]["study"]
    if study == "rq1":
        return tables.rq1_table(rows)
    if study == "rq2":
        return tables.rq2_table(rows)
    if study == "rq3":
        return tables.rq3_table(rows)
    if study == "repeat":
        return tables.repeat_table(rows, read_rows(ROWS / "study-rq2-test.jsonl"))
    return tables.adaptive_table(rows)


if __name__ == "__main__":
    raise SystemExit(main())
