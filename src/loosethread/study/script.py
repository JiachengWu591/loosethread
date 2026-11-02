"""RQ2's scripted interrogation: 8 turns per case, the same in every arm (STUDY_PLAN §5.2).

The script reads the truth so that it presses on the lie, which is why its rates describe a targeted
interrogation and not random play. Choices among innocents are drawn from the seed.
"""

import random
from dataclasses import dataclass
from enum import Enum

from loosethread.model import (
    Lang,
    LieReason,
    LocationId,
    PersonId,
    Query,
    QueryKind,
    SlotIndex,
    Statement,
)
from loosethread.study.arms import slot_start
from loosethread.study.cases import StudyCase


class TurnKind(Enum):
    WHERE = "where"  # says where, at a slot
    PRESSED = "pressed"  # "were you in the scene at that slot?"
    SAW = "saw"  # did you see the culprit at that slot?
    ITEM = "item"  # have you seen the stolen item?
    UNKNOWN = "unknown"  # who was in a room they were not in: knowledge they lack
    OUTSIDE = "outside"  # a time outside the evening: nothing to say


_TEMPLATES: dict[str, tuple[str, str]] = {
    "first": ("{t} 你在哪？", "Where were you at {t}?"),
    "second": ("{t} 的时候你人在什么地方？", "And you, where were you at {t}?"),
    "again": (
        "再确认一下，{t} 那会儿你到底在哪？",
        "Let me check that again: at {t}, where exactly were you?",
    ),
    "pressed": ("{t} 你是不是在{scene}？", "Were you in the {scene} at {t}?"),
    "saw": ("{t} 你看见{culprit}了吗？", "Did you see {culprit} at {t}?"),
    "item": ("你见过{item}吗？", "Have you seen the {item}?"),
    "unknown": ("{t} {room}里都有谁？", "Who was in the {room} at {t}?"),
    "outside": ("今天下午三点你在哪？", "Where were you at three this afternoon?"),
}  # fmt: skip


@dataclass(frozen=True)
class ScriptTurn:
    number: int
    kind: TurnKind
    addressee: PersonId
    question: str
    slot: SlotIndex | None = None
    about: PersonId | None = None  # SAW: whom they are asked about
    place: LocationId | None = None  # PRESSED or UNKNOWN: which room is named
    # What the question means, for turns where the game's reading is checked. None: no such query.
    query: Query | None = None


def lie_slot(sc: StudyCase) -> SlotIndex:
    """The theft slot, where the culprit's alibi lie is."""
    alibi = next(x for x in sc.case.truth.lies if x.reason is LieReason.ALIBI)
    return alibi.statement.claim.slot


def _witness(sc: StudyCase, slot: SlotIndex, innocents: list[PersonId]) -> PersonId:
    """A suspect whose answer about this slot exposes the lie, or else any innocent."""
    alibi = next(x for x in sc.case.truth.lies if x.reason is LieReason.ALIBI)
    exposers = [
        x.speaker
        for x in alibi.exposed_by
        if isinstance(x, Statement) and x.claim.slot == slot and x.speaker in innocents
    ]
    return sorted(set(exposers))[0] if exposers else innocents[0]


def interrogation(sc: StudyCase) -> tuple[ScriptTurn, ...]:
    view, truth, lang = sc.case.view, sc.case.truth, sc.lang
    rng = random.Random(f"loosethread:script:{sc.seed}")
    culprit = truth.culprit
    innocents = sorted(p for p in view.suspects if p != culprit)
    rng.shuffle(innocents)
    slot = lie_slot(sc)
    witness = _witness(sc, slot, innocents)
    others = [p for p in innocents if p != witness]
    item = view.world.items[0]
    names = {p.id: p.name.get(lang) for p in view.world.people}
    rooms = {x.id: x.name.get(lang) for x in view.world.locations}
    where = {(f.person, f.slot): f.location for f in truth.timeline}
    # A room the asked person was not in at that slot, and not the scene.
    asked = others[2]
    room = sorted(
        x.id
        for x in view.world.locations
        if x.id not in (where[(asked, slot)], view.crime.location)
    )[rng.randrange(len(view.world.locations) - 2)]

    def text(key: str) -> str:
        zh, en = _TEMPLATES[key]
        return (zh if lang is Lang.ZH else en).format(
            t=slot_start(sc, slot),
            scene=rooms[view.crime.location],
            culprit=names[culprit],
            item=item.name.get(lang),
            room=rooms[room],
        )

    def where_query(person: PersonId) -> Query:
        return Query(QueryKind.WHERE, person, slot=slot)

    return (
        ScriptTurn(1, TurnKind.WHERE, culprit, text("first"), slot, query=where_query(culprit)),
        ScriptTurn(2, TurnKind.WHERE, witness, text("second"), slot, query=where_query(witness)),
        ScriptTurn(3, TurnKind.WHERE, culprit, text("again"), slot, query=where_query(culprit)),
        ScriptTurn(
            4,
            TurnKind.PRESSED,
            culprit,
            text("pressed"),
            slot,
            place=view.crime.location,
            query=where_query(culprit),
        ),
        ScriptTurn(
            5,
            TurnKind.SAW,
            others[0],
            text("saw"),
            slot,
            about=culprit,
            query=Query(QueryKind.SAW_PERSON, others[0], person=culprit, slot=slot),
        ),
        ScriptTurn(
            6,
            TurnKind.ITEM,
            others[1],
            text("item"),
            query=Query(QueryKind.ABOUT_ITEM, others[1], item=item.id),
        ),
        ScriptTurn(7, TurnKind.UNKNOWN, asked, text("unknown"), slot, place=room),
        ScriptTurn(8, TurnKind.OUTSIDE, witness, text("outside")),
    )
