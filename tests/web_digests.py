"""Digests of cases and of whole games through the page's bridge. The same code runs in CPython and,
through `tests/web_node.mjs`, in the Pyodide build, and `tests/test_web_build.py` compares them."""

import dataclasses
import enum
import hashlib
import json

from loosethread.generator import daily_case
from loosethread.web import bridge

CASE_SEEDS = range(20260101, 20260141)
GAME_SEEDS = range(20260101, 20260106)


def _dumps(x: object) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def _canon(x: object) -> object:
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: _canon(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if isinstance(x, enum.Enum):
        return x.value
    if isinstance(x, dict):
        return sorted(([_canon(k), _canon(v)] for k, v in x.items()), key=_dumps)
    if isinstance(x, list | tuple):
        return [_canon(v) for v in x]
    if isinstance(x, set | frozenset):
        return sorted((_canon(v) for v in x), key=_dumps)
    return x


def _digest(x: object) -> str:
    return hashlib.sha256(_dumps(_canon(x)).encode("utf-8")).hexdigest()


def play(seed: int, lang: str) -> str:
    """Ask everyone about the theft window until a contradiction shows, then accuse from it."""
    reply = json.loads(bridge.start(seed, lang, ""))
    state = reply["state"]
    suspects = [p["id"] for p in state["sheet"]["people"] if p["suspect"]]
    grid = state["notes"]["grid"]
    times = grid["slots"][grid["first"] : grid["last"] + 1]
    replies = [reply]
    for time in times:
        for person in suspects:
            text = f"{time} 你在哪？" if lang == "zh" else f"Where were you at {time}?"
            reply = json.loads(bridge.ask(person, text))
            if reply["state"] is not None:
                replies.append(reply)
                state = reply["state"]
            if state["notes"]["conflicts"] or state["left"] == 0:
                break
        if state["notes"]["conflicts"] or state["left"] == 0:
            break
    conflicts = state["notes"]["conflicts"]
    first, second = (conflicts[0]["first"], conflicts[0]["second"]) if conflicts else ("E1", "E2")
    replies.append(json.loads(bridge.accuse(suspects[0], first, second)))
    return _digest(replies)


def digests() -> str:
    """A JSON object of every digest, for comparing two runs."""
    out = {f"case-{s}": _digest(daily_case(s)) for s in CASE_SEEDS}
    out |= {f"game-{s}-{lang}": play(s, lang) for s in GAME_SEEDS for lang in ("zh", "en")}
    return _dumps(out)
