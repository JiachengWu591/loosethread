"""The study's spending guard and the model wrapper that feeds it.

`ensure` is called by the runners between turns, not inside a model call, because `Game` treats any
exception from a parser as a parser failure and would turn "out of budget" into "please rephrase".
Costs are upper bounds (`Backend.cost`), and a call that fails is counted as nothing, since the
provider returns no usage for it.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loosethread.npc import Usage

if TYPE_CHECKING:
    from loosethread.llm.client import ChatModel, Completion

# CP-7: CNY 5 for tuning and the pilot. The full run needs the owner's separate approval, recorded
# here and in DECISIONS when given.
CAP_CNY = 5.0
ROWS = Path("results/rows")


class BudgetExceeded(RuntimeError):
    """The next step could pass the approved spending. Rows so far are kept."""


@dataclass
class Spend:
    limit: float
    spent: float = 0.0

    def ensure(self, reserve: float) -> None:
        """Stop before the running upper bound could pass the limit."""
        if self.spent + reserve > self.limit:
            raise BudgetExceeded(f"spent CNY {self.spent:.4f}, next step reserves {reserve:.4f}")


def spent_so_far(rows_dir: Path = ROWS) -> float:
    """CNY on every study row so far: tuning, pilot and test runs share one budget."""
    total = 0.0
    for path in sorted(rows_dir.glob("study-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            total += float(json.loads(line).get("cost_cny_max", 0.0))
    return total


class Metered:
    """A `ChatModel` that adds what each call cost to a `Spend`."""

    def __init__(self, model: "ChatModel", cost: Callable[[Usage], float], spend: Spend) -> None:
        self.model, self.cost, self.spend = model, cost, spend

    def complete(self, system: str, user: str, *, json_mode: bool, max_tokens: int) -> "Completion":
        reply = self.model.complete(system, user, json_mode=json_mode, max_tokens=max_tokens)
        self.spend.spent += self.cost(reply.usage)
        return reply
