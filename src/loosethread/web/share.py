"""The share card (DESIGN §9): spoiler-free by construction.

It is built only from the case number, the mark, the question count and one square per question, so
no name, place or time can reach it. `tests/test_web.py` checks this against real games.
"""

from collections.abc import Sequence

from loosethread.game import Outcome, Turn, Verdict
from loosethread.model import Lang

NOTHING_NEW, NEW_FACT, CONTRADICTION = "⬜", "🟨", "🟥"
LINK = "github.com/JiachengWu591/loosethread"


def squares(turns: Sequence[Turn]) -> str:
    """One square per question that cost one; free turns are not questions on the budget."""
    return "".join(
        CONTRADICTION if t.new_conflicts else NEW_FACT if t.new_notes else NOTHING_NEW
        for t in turns
        if t.cost
    )


def mark(verdict: Verdict) -> str:
    match verdict.outcome:
        case Outcome.SOLVED:
            return "★" * verdict.stars
        case Outcome.HUNCH:
            return "☆"
        case Outcome.WRONG:
            return "✗"


def share_card(seed: int, verdict: Verdict, turns: Sequence[Turn], lang: Lang) -> str:
    used, budget = verdict.questions_used, verdict.budget
    if lang is Lang.ZH:
        head, count = f"破绽 案件 #{seed} {mark(verdict)}", f"{used}/{budget} 问"
    else:
        head, count = f"Loose Thread case #{seed} {mark(verdict)}", f"{used}/{budget} questions"
    return "\n".join(line for line in (head, count, squares(turns), LINK) if line)
