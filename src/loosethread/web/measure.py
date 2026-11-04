"""P4's two model runs, with a key from the environment. Neither goes through a page.

python -m loosethread.web.measure lines  # CP-12: arm B on the pilot's 10 cases, beside the pilot
python -m loosethread.web.measure cost   # 20 scripted games through `WebSession`, 10 per language
python -m loosethread.web.measure adapter  # the page's own request code against the real API

Rows go to `results/rows/web-*.jsonl`, apart from the study's, whose budget is closed. D-043 allows
CNY 5 for all of P4, and the guard stops before the running upper bound passes it. It cannot count a
game the owner plays with their own key, which costs them and is not in these rows.
"""

import argparse
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from loosethread.llm.config import load_backends
from loosethread.model import Lang, PersonId
from loosethread.npc import Usage
from loosethread.stats import percentile
from loosethread.study.arms import Arm
from loosethread.study.cases import PILOT_SEEDS, development
from loosethread.study.metered import Metered, Spend
from loosethread.study.run import (
    Bench,
    commit_now,
    instrument_hashes,
    read_rows,
    run_rq2,
    write_rows,
)
from loosethread.study.tables import line_measures, rate, score_rq2
from loosethread.web.browser_chat import BrowserChat
from loosethread.web.session import BACKEND, WebSession

P4_CAP_CNY = 5.0  # D-043, for every row in `web-*.jsonl`
ROWS = Path("results/rows")
LINES_ROWS = ROWS / "web-lines-r1.jsonl"
COST_ROWS = ROWS / "web-cost-r1.jsonl"
COST_SEEDS = range(20261201, 20261221)
_RESERVE = 0.02  # CNY: more than any one turn has cost in these runs

type Row = dict[str, Any]


def spent_so_far() -> float:
    total = 0.0
    for path in sorted(ROWS.glob("web-*.jsonl")):
        total += sum(float(r.get("cost_cny_max", 0.0)) for r in read_rows(path))
    return total


def script(session: WebSession) -> list[tuple[str, str]]:
    """One player's game: everyone over the theft window until the budget ends, with one repeat and
    one bit of small talk along the way, since a real player spends turns on those too."""
    view, lang = session.game.case.view, session.game.lang
    world = view.world
    people = [p.id for p in world.people if p.id in view.suspects]
    turns: list[tuple[str, str]] = []
    for slot in view.crime.window:
        time = world.slots[slot].label.split("–")[0]
        for person in people:
            where = f"{time} 你在哪？" if lang is Lang.ZH else f"Where were you at {time}?"
            turns.append((person, where))
    turns.insert(3, turns[0])
    small = "今晚真冷。" if lang is Lang.ZH else "Cold night, isn't it?"
    turns.insert(6, (people[0], small))
    return turns


def play_game(session: WebSession) -> Row:
    for person, text in script(session):
        if session.game.left <= 0:
            break
        session.ask(person, text)
    game = session.game
    pairs = game.notebook.conflicts()
    suspects = sorted(game.case.view.suspects)
    evidence = game.case.view.evidence
    first, second = pairs[0] if pairs else (evidence[0].id, evidence[1].id)
    session.accuse(PersonId(suspects[0]), first, second)
    return {
        "seed": session.seed,
        "lang": game.lang.value,
        "turns": len(game.turns),
        "charged": game.used,
        "calls": sum(t.parse_usage.calls + t.line_usage.calls for t in game.turns),
        "prompt_tokens": sum(
            t.parse_usage.prompt_tokens + t.line_usage.prompt_tokens for t in game.turns
        ),
        "completion_tokens": sum(
            t.parse_usage.completion_tokens + t.line_usage.completion_tokens for t in game.turns
        ),
        "turn_seconds": [
            round(t.parse_usage.seconds + t.line_usage.seconds, 3) for t in game.turns
        ],
        "problems": [p for t in game.turns for p in t.problems],
        "lines": [t.line for t in game.turns],
    }


def run_cost() -> list[Row]:
    from loosethread.llm.client import open_model  # noqa: PLC0415

    model = open_model(BACKEND)
    spend = Spend(P4_CAP_CNY, spent_so_far())
    metered = Metered(model, model.backend.cost, spend)
    commit = commit_now()
    rows: list[Row] = []
    for seed in COST_SEEDS:
        lang = Lang.ZH if seed % 2 == 0 else Lang.EN
        spend.ensure(_RESERVE * 40)
        session = WebSession(seed, lang)
        session.use_model(metered)
        row = play_game(session)
        usage = Usage(
            prompt_tokens=row["prompt_tokens"], completion_tokens=row["completion_tokens"]
        )
        rows.append(
            row
            | {
                "commit": commit,
                "model": model.backend.model,
                "cost_cny_max": round(model.backend.cost(usage), 6),
            }
        )
        write_rows(COST_ROWS, rows)
        print(seed, lang.value, row["charged"], rows[-1]["cost_cny_max"], flush=True)
    return rows


def _plain_send(
    method: str, url: str, headers: Mapping[str, str], body: str | None, timeout: float
) -> tuple[int, str]:
    """What `xhr_send` does in a browser, for a run outside one. A failed reply is dropped."""
    data = None if body is None else body.encode("utf-8")
    request = urllib.request.Request(url, data, dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return int(reply.status), reply.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return int(err.code), ""
    except OSError:
        return 0, ""


def run_adapter() -> list[Row]:
    """`BrowserChat`'s request against the real API, with the key from the environment, and a real
    game on top. It shows the API accepts what the page's code sends and the code reads the reply.
    It cannot show that a browser sends it the same way: only a game in a browser can."""
    backend = load_backends()[BACKEND]
    key = os.environ.get(backend.api_key_env, "")
    if not key:
        raise SystemExit(f"environment variable {backend.api_key_env} is not set")
    chat = BrowserChat(backend, key, _plain_send)
    chat.check_model()
    session = WebSession(20261108, Lang.ZH)
    session.use_model(chat)
    people = sorted(session.game.case.view.suspects)
    for person, text in (
        (people[0], "八点一刻你在哪？"),
        (people[1], "你八点半跟谁在一起？"),
        (people[0], "八点一刻你到底在哪？"),
    ):
        session.ask(person, text)
    game = session.game
    usage = Usage(prompt_tokens=session.prompt_tokens, completion_tokens=session.completion_tokens)
    row = {
        "commit": commit_now(),
        "model": backend.model,
        "turns": len(game.turns),
        "charged": game.used,
        "calls": sum(t.parse_usage.calls + t.line_usage.calls for t in game.turns),
        "problems": [p for t in game.turns for p in t.problems],
        "lines": [t.line for t in game.turns],
        "cost_cny_max": round(backend.cost(usage), 6),
    }
    write_rows(ROWS / "web-adapter-r1.jsonl", [row])
    return [row]


def run_lines() -> list[Row]:
    from loosethread.llm.client import open_model  # noqa: PLC0415

    model = open_model(BACKEND)
    spend = Spend(min(P4_CAP_CNY, spent_so_far() + 1.0), spent_so_far())
    bench = Bench(
        Metered(model, model.backend.cost, spend),
        model.backend.cost,
        spend,
        commit_now(),
        model.backend.model,
        instrument_hashes(),
        path=LINES_ROWS,
    )
    return run_rq2(bench, "pilot", development(PILOT_SEEDS)[:10], [Arm.B])


# --- Tables ----------------------------------------------------------------------------------


def lines_table(after: Sequence[Row], before: Sequence[Row]) -> list[str]:
    """CP-12's regression. It shows the check still holds and the repeats changed. Whether the lines
    read better is for the owner's game."""
    earlier = [r for r in before if r["arm"] == "B"]
    out: list[str] = []
    for title, rows in (("Before, the pilot's arm B", earlier), ("After CP-12", after)):
        sessions = score_rq2(rows)
        failed = sum(s.failed for s in sessions)
        valid = sum(s.valid for s in sessions)
        legitimate = sum(s.legitimate for s in sessions)
        out += [
            f"{title}: {len(rows)} turns in {len(sessions)} cases",
            f"  sessions with a failure: {rate(failed, len(sessions))}",
            f"  valid answers, turns 1 to 6: {rate(valid, legitimate)}",
            *line_measures(rows)[1:],
        ]
    return out


def _spread(values: list[float], digits: int) -> str:
    return (
        f"median {statistics.median(values):.{digits}f},"
        f" p95 {percentile(values, 95):.{digits}f}, most {max(values):.{digits}f}"
    )


def cost_table(rows: Sequence[Row], spent: float) -> list[str]:
    """Per game, with the model's own lines. Costs are upper bounds (`Backend.cost`)."""
    turn_seconds = [s for r in rows for s in r["turn_seconds"]]
    turns = sum(int(r["turns"]) for r in rows)
    failed = [p for r in rows for p in r["problems"]]
    replaced = sum("line_" in p or "writer_" in p for p in failed)
    unreachable = sum("unavailable" in p for p in failed)
    costs = [float(r["cost_cny_max"]) for r in rows]
    return [
        f"Scripted games: {len(rows)}, on {rows[0]['model']} at commit {rows[0]['commit'][:7]}",
        "  each is everyone over the theft window until the budget ends, plus one repeat and"
        " one bit of small talk",
        f"CNY per game, upper bound: {_spread(costs, 3)}",
        f"Questions charged per game: {_spread([float(r['charged']) for r in rows], 0)}",
        f"Model calls per game: {_spread([float(r['calls']) for r in rows], 0)}",
        f"Seconds per turn in the model: {_spread(turn_seconds, 1)}",
        f"Lines the template replaced: {rate(replaced, turns)}",
        f"Turns that could not reach the model: {rate(unreachable, turns)}",
        f"P4 model spending so far, upper bound: CNY {spent:.2f} of {P4_CAP_CNY:.2f}",
        "These are scripted questions, in a loop no player would write. The owner's own game is"
        " not in these rows.",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loosethread.web.measure", description=__doc__)
    parser.add_argument("run", choices=["lines", "cost", "adapter"])
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.run == "adapter":
        print(json.dumps(run_adapter(), ensure_ascii=False, indent=1))
    elif args.run == "lines":
        rows = run_lines()
        before = read_rows(ROWS / "study-rq2-pilot-r1.jsonl")
        print("\n".join(lines_table(rows, before)))
    else:
        print("\n".join(cost_table(run_cost(), spent_so_far())))
    print(json.dumps({"p4_spent_cny_max": round(spent_so_far(), 4)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
