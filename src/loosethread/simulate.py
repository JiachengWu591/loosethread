"""Simulated systematic player: a second difficulty metric (CP-1 option C, D-018 item 5).

The oracle `min_questions` assumes the player already knows whom to ask about which slot. This
player knows nothing about the truth. It asks every suspect "who was with you" for every slot of
the theft window in a random order (what the owner did in the first playtest), then the client
about the window, then every other question in a random order. After each answer it checks what
a careful player could check with the notebook alone:

- identified: the full solver, run on the testimony obtained so far, leaves exactly one suspect;
- solved: identified, and the notebook holds a pair that would score as an exposed lie.

The solver is a perfect reasoner, so this measures how much testimony a case needs, not how hard
it is to see the deduction. Orders are seeded per case, so results are reproducible.

python -m loosethread.simulate --seeds 200 --orders 20
python -m loosethread.simulate --game --budget 12   # the cases the game plays (D-031), per shape
"""

import argparse
import json
import math
import random
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from loosethread.difficulty import question_plan
from loosethread.game import DEFAULT_BUDGET, Game, StarRule
from loosethread.generator import DAILY, AlibiStyle, daily_case, daily_setup, generate
from loosethread.lines import TemplateWriter
from loosethread.lookup import in_scope_queries
from loosethread.model import Case, Lang, Query, QueryKind
from loosethread.parser import RuleParser, canonical_question
from loosethread.solver import Solver
from loosethread.stats import percentile, wilson

ROWS = Path("results/rows/simulated-player.jsonl")
GAME_ROWS = Path("results/rows/simulated-player-game.jsonl")
STAR_RUNS = 20  # simulated players behind each case's star thresholds (CP-5)
CP5_BUDGET = 20  # the budget CP-5 was measured with; the summary's default, to reproduce it
OLD_TWO_STARS_SHARE = 0.7  # the oracle-based rule before CP-5, kept to reproduce its evidence


@dataclass(frozen=True)
class Run:
    seed: int
    order: int
    min_questions: int
    window: int  # slots in the theft window
    suspects: int
    identified_at: int | None  # questions asked when one suspect was left
    solved_at: int | None  # questions asked when an exposing pair was also in the notebook
    pack: str = "mistpine"  # the defaults describe the rows from before step 4b
    shape: str = AlibiStyle.OCCUPIED.value


def question_order(case: Case, rng: random.Random) -> list[Query]:
    view = case.view
    window = list(view.crime.window)
    suspects = sorted(view.suspects)
    first = [Query(QueryKind.WITH_WHOM, s, slot=t) for s in suspects for t in window]
    others = sorted(p.id for p in view.world.people if p.id not in view.suspects)
    second = [Query(QueryKind.WITH_WHOM, p, slot=t) for p in others for t in window]
    rng.shuffle(first)
    rng.shuffle(second)
    asked = set(first) | set(second)
    rest = [q for q in in_scope_queries(view.world) if q not in asked]
    rng.shuffle(rest)
    return first + second + rest


def _solve(case: Case, rng: random.Random) -> tuple[int | None, int | None]:
    """Questions asked when the culprit was identified, and when the case was solved."""
    queries = question_order(case, rng)
    game = Game(case, RuleParser(), TemplateWriter(), Lang.EN, budget=len(queries))
    world = case.view.world
    identified_at = None
    for query in queries:
        turn = game.ask(query.addressee, canonical_question(query, world, Lang.EN))
        if not turn.new_notes:
            continue
        if identified_at is None:
            if Solver(game.notebook.obtained_view()).consistent().unique is None:
                continue
            identified_at = game.used
        if any(game.exposes_culprit_lie(*pair) for pair in game.notebook.conflicts()):
            return identified_at, game.used
    return identified_at, None


def play(
    case: Case, seed: int, order: int, min_questions: int, shape: AlibiStyle = AlibiStyle.OCCUPIED
) -> Run:
    identified_at, solved_at = _solve(case, random.Random(f"{seed}:{order}"))
    view = case.view
    return Run(
        seed,
        order,
        min_questions,
        len(view.crime.window),
        len(view.suspects),
        identified_at,
        solved_at,
        view.pack_id,
        shape.value,
    )


def star_rule(case: Case, budget: int = DEFAULT_BUDGET, orders: int = STAR_RUNS) -> StarRule:
    """CP-5: ★★★ up to the fastest quarter of simulated systematic players, ★★ up to their
    median, both capped at the budget. Deterministic: the orders do not depend on the truth."""
    done = []
    for order in range(orders):
        _, solved_at = _solve(case, random.Random(f"stars:{order}"))
        done.append(float(solved_at) if solved_at is not None else math.inf)
    three, two = percentile(done, 25), percentile(done, 50)
    return StarRule(int(min(three, budget)), int(min(two, budget)))


def simulate(seeds: Sequence[int], orders: int) -> list[Run]:
    runs = []
    for seed in seeds:
        case = generate(seed, DAILY).case
        min_q = len(question_plan(case.view, Solver(case.view))[0])
        runs += [play(case, seed, order, min_q) for order in range(orders)]
    return runs


def simulate_game(seeds: Sequence[int], orders: int) -> list[Run]:
    """The same players on the cases the game plays."""
    runs = []
    for seed in seeds:
        case = daily_case(seed).case
        shape = daily_setup(seed)[1]
        min_q = len(question_plan(case.view, Solver(case.view))[0])
        runs += [play(case, seed, order, min_q, shape) for order in range(orders)]
    return runs


def by_group(runs: Sequence[Run], budget: int) -> list[str]:
    """Per lie shape and per setting. Rates are over cases, each represented by its median run."""
    lines: list[str] = []
    for field in ("shape", "pack"):
        groups: dict[str, dict[int, list[Run]]] = {}
        for run in runs:
            groups.setdefault(getattr(run, field), {}).setdefault(run.seed, []).append(run)
        for name, cases in sorted(groups.items()):
            never = budget * 1000
            medians = [
                statistics.median(r.solved_at if r.solved_at is not None else never for r in rs)
                for rs in cases.values()
            ]
            n, within = len(cases), sum(m <= budget for m in medians)
            lo, hi = wilson(within, n)
            oracle = statistics.median(rs[0].min_questions for rs in cases.values())
            lines.append(
                f"  {name}: {n} cases; oracle minimum median {oracle:.0f};"
                f" questions to solve, median run: median {statistics.median(medians):.0f},"
                f" p90 {percentile([float(m) for m in medians], 90):.0f};"
                f" within {budget}: {within}/{n} = {within / n:.1%}"
                f" [Wilson 95%: {lo:.1%}, {hi:.1%}]"
            )
    return lines


def summary(runs: Sequence[Run], budget: int = CP5_BUDGET) -> list[str]:
    """Case-level rates with Wilson intervals: the orders of one case are not independent, so the
    case is the unit. Each case is represented by its median run (and, once, by its best run)."""
    by_case: dict[int, list[Run]] = {}
    for run in runs:
        by_case.setdefault(run.seed, []).append(run)
    n = len(by_case)
    orders = len(runs) // n if n else 0
    lines = [f"{len(runs)} runs: {n} cases x {orders} orders; rates are over cases"]

    def rate(label: str, k: int) -> None:
        lo, hi = wilson(k, n)
        lines.append(f"  {label}: {k}/{n} = {k / n:.1%} [Wilson 95%: {lo:.1%}, {hi:.1%}]")

    never = budget * 1000  # an unsolved run counts as needing more than any budget
    median = {
        s: statistics.median(r.solved_at if r.solved_at is not None else never for r in rs)
        for s, rs in by_case.items()
    }
    best = {s: min(r.solved_at or never for r in rs) for s, rs in by_case.items()}
    first = {s: rs[0] for s, rs in by_case.items()}
    medians = sorted(float(m) for m in median.values())
    lines.append(
        f"  questions to solve, per-case median run: median {statistics.median(medians):.0f},"
        f" p90 {percentile(medians, 90):.0f}, max {max(medians):.0f}"
    )
    sweeps = sorted({r.suspects * r.window for r in first.values()})
    lines.append(f"  first sweep (suspects x window): {sweeps} questions; budget {budget}")
    rate(
        "solved inside the first sweep (median run)",
        sum(median[s] <= first[s].suspects * first[s].window for s in by_case),
    )
    rate("median run within the budget", sum(m <= budget for m in median.values()))
    two = int(OLD_TWO_STARS_SHARE * budget)  # the rule before CP-5
    rate(f"before CP-5: median run within ★★ ({two})", sum(m <= two for m in median.values()))
    rate(
        "before CP-5: median run within ★★★ (minimum + 2)",
        sum(median[s] <= first[s].min_questions + 2 for s in by_case),
    )
    rate(
        "before CP-5: best of the orders within ★★★",
        sum(best[s] <= first[s].min_questions + 2 for s in by_case),
    )
    rate(
        "some order identifies the culprit before an exposing pair is noted",
        sum(any(r.identified_at != r.solved_at for r in rs) for rs in by_case.values()),
    )
    gaps = [
        float(r.solved_at - r.identified_at)
        for r in runs
        if r.solved_at is not None and r.identified_at is not None
    ]
    late = [g for g in gaps if g > 0]
    lines.append(
        f"  runs (descriptive, correlated within cases): {len(late)}/{len(runs)} identify first,"
        f" then need {statistics.fmean(late) if late else 0:.1f} more questions on average"
    )
    return lines


def load_runs(path: Path) -> list[Run]:
    return [Run(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loosethread.simulate", description=__doc__)
    parser.add_argument("--seeds", type=int, default=200, help="daily cases 0..N-1")
    parser.add_argument("--orders", type=int, default=20, help="random orders per case")
    parser.add_argument("--game", action="store_true", help="the cases the game plays (D-031)")
    parser.add_argument("--out", type=Path, help=f"default {ROWS}, or {GAME_ROWS} with --game")
    parser.add_argument("--score", type=Path, help="only recompute the summary from rows")
    parser.add_argument(
        "--budget", type=int, default=CP5_BUDGET, help=f"for the summary (game: {DEFAULT_BUDGET})"
    )
    args = parser.parse_args(argv)
    if args.score:
        runs = load_runs(args.score)
    else:
        runs = (simulate_game if args.game else simulate)(range(args.seeds), args.orders)
        out: Path = args.out or (GAME_ROWS if args.game else ROWS)
        out.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(asdict(r)) + "\n" for r in runs)
        out.write_text(text, encoding="utf-8", newline="\n")
    print("\n".join(summary(runs, args.budget)))
    if args.game or len({r.shape for r in runs}) > 1:
        print("\n".join(by_group(runs, args.budget)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
