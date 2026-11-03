"""Recomputes every table in `results/` from `results/rows/`, offline and with no key.

python -m loosethread.verify          # compares with the files; exit 1 on any difference
python -m loosethread.verify --write  # writes the files

It repeats every scoring decision from the raw rows. It cannot show that the rows came from the
calls they describe, or that a model would answer the same way again.
"""

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from loosethread import parser_eval, simulate
from loosethread.game import DEFAULT_BUDGET
from loosethread.generator import daily_case
from loosethread.study import checks, control, rq1, tables
from loosethread.study.cases import held_out, study_case
from loosethread.study.metered import CAP_CNY
from loosethread.study.tables import rate

RESULTS = Path("results")
ROWS = RESULTS / "rows"
OWNER = ROWS / "study-owner-checks.jsonl"  # the owner's own answers, and reviews they delegated
GENERATOR_SEEDS = 300  # the attempt-level figure in STUDY_PLAN §5.1

type Row = dict[str, Any]


def _rows(name: str) -> list[Row]:
    path = ROWS / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _owner(check: str) -> list[Row]:
    if not OWNER.exists():
        return []
    return [r for r in _rows(OWNER.name) if r["check"] == check]


def judge_decisions() -> dict[tuple[str, str], bool]:
    return {(str(r["arm"]), str(r["attack"])): bool(r["leak"]) for r in _owner("judge")}


def parser_tables() -> list[str]:
    lines = []
    for name, title in (("deepseek", "DeepSeek"), ("rule", "Rules"), ("local", "Local Qwen")):
        lines += parser_eval.report(_rows(f"parser-{name}-test.jsonl"), title)
    lines.append(
        "DeepSeek vs rules: "
        + parser_eval.compare(_rows("parser-deepseek-test.jsonl"), _rows("parser-rule-test.jsonl"))
    )
    return lines


def simulated_tables() -> list[str]:
    classic = simulate.load_runs(simulate.ROWS)
    game = simulate.load_runs(simulate.GAME_ROWS)
    return [
        "The classic generator, budget 20 (CP-5):",
        *simulate.summary(classic),
        "",
        f"The cases the game plays, budget {DEFAULT_BUDGET}:",
        *simulate.summary(game, DEFAULT_BUDGET),
        *simulate.by_group(game, DEFAULT_BUDGET),
    ]


def rq1_tables() -> list[str]:
    from loosethread.study.run import judge_written  # noqa: PLC0415

    lines = tables.rq1_table(_rows("study-rq1-deepseek-think-long-test.jsonl"))
    lines += tables.rq1_table(_rows("study-rq1-test.jsonl"))
    verdicts: Counter[str] = Counter()
    for seed, lang in held_out():
        sc = study_case(seed, lang)
        verdicts[str(judge_written(rq1.generator_reply(sc.case), "stop", sc)["verdict"])] += 1
    lines.append(
        "Control: the generator's test cases through the same checker, which pass by construction"
        " and so check the checker: " + ", ".join(f"{k} {v}" for k, v in sorted(verdicts.items()))
    )
    attempts = sum(daily_case(seed).attempts for seed in range(GENERATOR_SEEDS))
    lines.append(
        f"Comparison: the generator's attempts accepted, seeds 0-{GENERATOR_SEEDS - 1}:"
        f" {rate(GENERATOR_SEEDS, attempts)}"
    )
    return lines


def rq2_tables() -> list[str]:
    rows = _rows("study-rq2-test.jsonl")
    return [
        *tables.rq2_table(rows),
        *tables.rq2_groups(rows),
        *tables.line_measures(rows),
        *tables.rq2_post_hoc(rows),
    ]


def judge_check_tables() -> list[str]:
    return control.control_table(_rows(control.OUT.name))


def rq3_tables() -> list[str]:
    return tables.rq3_table(_rows("study-rq3-test.jsonl"), judge_decisions())


def unhardened_tables() -> list[str]:
    return tables.unhardened_table(
        _rows("study-rq3-U-test.jsonl"), _rows("study-rq3-test.jsonl"), judge_decisions()
    )


def adaptive_tables() -> list[str]:
    lines: list[str] = []
    for arm in ("A", "B"):
        for lang in ("zh", "en"):
            lines += tables.adaptive_table(_rows(f"study-adaptive-{arm}-{lang}-test.jsonl"))
    return lines


def repeat_tables() -> list[str]:
    return tables.repeat_table(_rows("study-repeat-test.jsonl"), _rows("study-rq2-test.jsonl"))


def hypotheses_tables() -> list[str]:
    return tables.hypotheses_table(
        _rows("study-rq1-deepseek-think-long-test.jsonl"),
        _rows("study-rq2-test.jsonl"),
        _rows("study-rq3-test.jsonl"),
        judge_decisions(),
    )


def owner_tables() -> list[str]:
    extractor = _owner("extractor")
    judge = _owner("judge")
    flagged = _owner("flagged")
    pairs = _owner("pair")
    if not (extractor or judge or flagged or pairs):
        return ["The owner's checks are not in yet."]
    right = sum(bool(r["correct"]) for r in extractor)
    reviewed = [*extractor, *judge, *flagged]
    agree = sum(r["r1"] == r["r2"] for r in reviewed)
    registered = [r for r in judge if r["sheet"] == "judge"]
    control_part = [r for r in judge if r["sheet"] == "judge-u"]
    rq2 = _rows("study-rq2-test.jsonl")
    lines = [
        f"Read by {reviewed[0]['by']}, not by a person.",
        f"  the two runs give the same verdict: {rate(agree, len(reviewed))}",
        "  they are one model twice, so this does not show independent judges agree",
        f"Extractor, 30 test lines, right if both say so: {rate(right, len(extractor))}",
        "  fewer than 27 right, so the report carries the plan's caveat (STUDY_PLAN §8)",
        f"Judge sheet, arms A, B, C: {len(registered)} items,"
        f" leaks if either says so: {sum(bool(r['leak']) for r in registered)}",
        f"Judge sheet, arm U: {len(control_part)} items,"
        f" leaks if either says so: {sum(bool(r['leak']) for r in control_part)}",
    ]
    verdicts = [bool(r["real"]) for r in sorted(flagged, key=lambda r: int(r["number"]))]
    lines += checks.flagged_table(rq2, verdicts)
    if pairs:
        answers = [str(r["answer"]) for r in sorted(pairs, key=lambda r: int(r["number"]))]
        lines += checks.pairs_table(rq2, answers)
    else:
        lines.append("Line pairs: the owner's blind rating is not in yet.")
    return lines


def _spend_group(name: str) -> str:
    if "-tune" in name or "-pilot" in name or "check" in name:
        return "tuning, pilot and checks"
    if "rq3-U" in name:
        return "RQ3, control for the attacks"
    if "rq1-deepseek-think-long" in name:
        return "RQ1, thinking on"
    for key, group in (
        ("rq1", "RQ1, thinking off"),
        ("rq2", "RQ2"),
        ("rq3", "RQ3, static"),
        ("adaptive", "RQ3, adaptive"),
        ("repeat", "run-to-run repeat"),
    ):
        if key in name:
            return group
    return "other"


def spend_tables() -> list[str]:
    groups: dict[str, float] = {}
    for path in sorted(ROWS.glob("study-*.jsonl")):
        spent = sum(float(r.get("cost_cny_max", 0.0)) for r in _rows(path.name))
        group = _spend_group(path.name)
        groups[group] = groups.get(group, 0.0) + spent
    return [
        "Study spend, upper bound (peak price, no cache discount, prices of 2026-10-31)",
        *[f"  {k}: CNY {v:.2f}" for k, v in sorted(groups.items())],
        f"  total: CNY {sum(groups.values()):.2f} of {CAP_CNY:.2f}",
    ]


TABLES: dict[str, tuple[str, Callable[[], Sequence[str]]]] = {
    "hypotheses.md": ("Hypotheses against the numbers", hypotheses_tables),
    "rq1.md": ("RQ1: solvability", rq1_tables),
    "rq2.md": ("RQ2: consistency, and the cost of valid answers", rq2_tables),
    "rq3.md": ("RQ3: static attacks", rq3_tables),
    "rq3-unhardened.md": ("RQ3: a control for the attacks (post hoc, CP-10)", unhardened_tables),
    "adaptive.md": ("RQ3: adaptive campaigns", adaptive_tables),
    "judge-check.md": ("Can the judge see a leak? (post hoc)", judge_check_tables),
    "repeat.md": ("Run-to-run stability", repeat_tables),
    "owner-checks.md": ("The owner's checks", owner_tables),
    "spend.md": ("Spending", spend_tables),
    "parser.md": ("Parser on the frozen test set (P2)", parser_tables),
    "simulated-player.md": ("Simulated players (P1, P2)", simulated_tables),
}


def render(title: str, lines: Sequence[str]) -> str:
    body = "\n".join(lines)
    return (
        f"# {title}\n\nComputed from `results/rows/` by `python -m loosethread.verify`."
        f"\n\n```text\n{body}\n```\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loosethread.verify", description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the files in results/")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    differing: list[str] = []
    for name, (title, compute) in TABLES.items():
        text = render(title, compute())
        path = RESULTS / name
        if args.write:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path}")
        elif not path.exists() or path.read_text(encoding="utf-8") != text:
            differing.append(name)
            print(f"DIFFERS {path}")
        else:
            print(f"same    {path}")
    if differing:
        print(f"{len(differing)} tables differ from their rows")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
