"""The player's notebook: evidence plus every claim obtained by asking, with contradiction hints.

Reads only the player's view. Hints compare obtained items only (DESIGN §8): a pair is flagged when
the two cannot both be true under the solver's direct-conflict rule (same person, same slot,
different places; or an impossible move between neighbouring slots). The player still has to work
out which side is the lie.
"""

from dataclasses import replace

from loosethread.model import (
    Basis,
    Evidence,
    ItemAt,
    Lang,
    Occupants,
    PersonAt,
    PersonId,
    PlayerView,
    Query,
    Statement,
    Testimony,
    World,
)
from loosethread.solver import Solver

_NOTES: dict[str, tuple[str, str]] = {
    "self_at": ("{s}：{t} 自己在{loc}", "{s}: in the {loc} at {t}"),
    "alone": ("{s}：{t} 独自在{loc}", "{s}: alone in the {loc} at {t}"),
    "with": ("{s}：{t} 在{loc}，同在的有{others}", "{s}: in the {loc} at {t} with {others}"),
    "saw": ("{s}：{t} 在{loc}见到{p}", "{s}: saw {p} in the {loc} at {t}"),
    "heard": (
        "{s}：听{src}说，{t} {p}在{loc}",
        "{s}: heard from {src} that {p} was in the {loc} at {t}",
    ),
    "heard_self": (
        "{s}：听{src}说，{t} {src}自己在{loc}",
        "{s}: heard from {src} that they were in the {loc} at {t}",
    ),
    "item": ("{s}：{t} 在{loc}见过{item}", "{s}: saw the {item} in the {loc} at {t}"),
}  # fmt: skip


def effective_speaker(s: Statement) -> PersonId:
    """Whose claim this is: the source, for hearsay (T5)."""
    return s.source if s.basis is Basis.HEARSAY and s.source is not None else s.speaker


def describe(s: Statement, world: World, lang: Lang) -> str:
    """One notebook line for a statement, in the third person; times are slot starts."""
    person = {p.id: p.name.get(lang) for p in world.people}
    loc = {x.id: x.name.get(lang) for x in world.locations}
    item = {i.id: i.name.get(lang) for i in world.items}
    order = [p.id for p in world.people]
    start = {int(x.index): x.label.split("–")[0] for x in world.slots}

    def t(key: str, **fields: object) -> str:
        zh, en = _NOTES[key]
        return (zh if lang is Lang.ZH else en).format(s=person[s.speaker], **fields)

    match s.claim:
        case PersonAt(p, where, slot) if s.basis is Basis.HEARSAY and s.source is not None:
            key = "heard_self" if p == s.source else "heard"
            return t(key, src=person[s.source], p=person[p], t=start[slot], loc=loc[where])
        case PersonAt(p, where, slot) if p == s.speaker:
            return t("self_at", t=start[slot], loc=loc[where])
        case PersonAt(p, where, slot):
            return t("saw", p=person[p], t=start[slot], loc=loc[where])
        case Occupants(where, slot, people):
            others = [person[p] for p in order if p in people and p != s.speaker]
            if not others:
                return t("alone", t=start[slot], loc=loc[where])
            sep = "、" if lang is Lang.ZH else ", "
            return t("with", t=start[slot], loc=loc[where], others=sep.join(others))
        case ItemAt(thing, where, slot):
            return t("item", item=item[thing], t=start[slot], loc=loc[where])


def _order(note_id: str) -> tuple[int, int]:
    return (0 if note_id.startswith("S") else 1, int(note_id[1:]))


class Notebook:
    def __init__(self, view: PlayerView) -> None:
        self.view = view
        self._answers: list[Testimony] = []
        self._ids: dict[Statement, str] = {}
        self._conflicts: tuple[tuple[str, str], ...] = ()

    def record(self, query: Query, claims: tuple[Statement, ...]) -> tuple[str, ...]:
        """Add one answer; returns the ids given to claims not recorded before."""
        if not claims:
            return ()
        self._answers.append(Testimony(query, claims))
        new = []
        for claim in claims:
            if claim not in self._ids:
                self._ids[claim] = f"S{len(self._ids) + 1}"
                new.append(self._ids[claim])
        if new:
            self._conflicts = self._compute_conflicts()
        return tuple(new)

    @property
    def statements(self) -> tuple[tuple[str, Statement], ...]:
        return tuple((note_id, s) for s, note_id in self._ids.items())

    def lookup(self, note_id: str) -> Statement | Evidence | None:
        key = note_id.strip().upper()
        for s, found in self._ids.items():
            if found == key:
                return s
        return next((e for e in self.view.evidence if e.id.upper() == key), None)

    def obtained_view(self) -> PlayerView:
        """The player's view restricted to the testimony obtained so far."""
        return replace(self.view, testimony=tuple(self._answers))

    def conflicts(self) -> tuple[tuple[str, str], ...]:
        """Pairs of obtained items (statement, statement or evidence) that cannot both be true."""
        return self._conflicts

    def _compute_conflicts(self) -> tuple[tuple[str, str], ...]:
        solver = Solver(self.obtained_view())
        pairs: set[tuple[str, str]] = set()
        for a, b in solver.conflict_pairs():
            ids = [self._ids[solver.statements[a]]]
            ids.append(self._ids[solver.statements[b]] if isinstance(b, int) else str(b))
            first, second = sorted(ids, key=_order)
            pairs.add((first, second))
        return tuple(sorted(pairs, key=lambda p: (_order(p[0]), _order(p[1]))))
