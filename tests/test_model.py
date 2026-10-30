"""Tests for the data contracts: validation, immutability and structural truth isolation."""

import dataclasses
import typing
from typing import Any

import pytest

from loosethread.model import (
    AllowedFacts,
    Basis,
    Case,
    CrimeReport,
    Event,
    Evidence,
    EvidenceId,
    EvidenceKind,
    Item,
    ItemId,
    Knowledge,
    Lang,
    Lie,
    LieReason,
    LocalizedText,
    Location,
    LocationId,
    Occupants,
    Person,
    PersonAt,
    PersonId,
    PlayerView,
    Query,
    QueryKind,
    SlotIndex,
    Stance,
    Statement,
    TimeSlot,
    Truth,
    World,
)

TRUTH_TYPES = frozenset({Truth, Lie, Knowledge, Event, Case})

LIN, ZHOU, CLIENT = PersonId("lin"), PersonId("zhou"), PersonId("client")
STUDY, CORRIDOR, LOBBY = LocationId("study"), LocationId("corridor"), LocationId("lobby")
SEAL = ItemId("seal")


def _text(s: str) -> LocalizedText:
    return LocalizedText(zh=s, en=s)


def _person(pid: PersonId) -> Person:
    return Person(id=pid, name=_text(pid), role=_text("guest"), persona=_text("plain"))


def _location(lid: LocationId, *neighbors: LocationId) -> Location:
    return Location(id=lid, name=_text(lid), neighbors=frozenset(neighbors))


def _slots(n: int) -> tuple[TimeSlot, ...]:
    return tuple(TimeSlot(SlotIndex(i), 20 * 60 + 15 * i, 20 * 60 + 15 * (i + 1)) for i in range(n))


def _world() -> World:
    return World(
        people=(_person(LIN), _person(ZHOU), _person(CLIENT)),
        locations=(
            _location(STUDY, CORRIDOR),
            _location(CORRIDOR, STUDY, LOBBY),
            _location(LOBBY, CORRIDOR),
        ),
        slots=_slots(4),
        items=(Item(SEAL, _text("jade seal"), owner=CLIENT),),
    )


def _view() -> PlayerView:
    seen = Statement(LIN, PersonAt(LIN, LOBBY, SlotIndex(1)), Basis.WITNESSED)
    return PlayerView(
        seed=7,
        world=_world(),
        suspects=frozenset({LIN, ZHOU}),
        motives=(),
        crime=CrimeReport(SEAL, STUDY, last_seen=SlotIndex(0), discovered=SlotIndex(3)),
        evidence=(
            Evidence(
                EvidenceId("e1"),
                EvidenceKind.PHOTO,
                (PersonAt(ZHOU, CORRIDOR, SlotIndex(1)),),
                _text("photo"),
            ),
        ),
        statements=(seen,),
    )


# --- Structural isolation -----------------------------------------------------------------------


def _reachable_types(root: type) -> set[type]:
    """All classes reachable from `root` through dataclass field annotations."""
    seen: set[type] = set()
    stack: list[Any] = [root]
    while stack:
        tp = stack.pop()
        if isinstance(tp, typing.TypeAliasType):
            stack.append(tp.__value__)
        elif isinstance(tp, typing.NewType):
            stack.append(tp.__supertype__)
        elif typing.get_args(tp):
            stack.extend(typing.get_args(tp))
        elif isinstance(tp, type) and tp not in seen:
            seen.add(tp)
            if dataclasses.is_dataclass(tp):
                stack.extend(typing.get_type_hints(tp).values())
    return seen


def test_walker_finds_truth_from_case() -> None:
    # Guards against a vacuous isolation test: the walker must see truth types where they exist.
    assert TRUTH_TYPES - {Case} <= _reachable_types(Case)


@pytest.mark.parametrize("root", [PlayerView, AllowedFacts])
def test_no_truth_type_reachable(root: type) -> None:
    assert _reachable_types(root) & TRUTH_TYPES == set()


def test_statement_has_no_truth_flag() -> None:
    names = {f.name for f in dataclasses.fields(Statement)}
    assert names == {"speaker", "claim", "basis", "source"}


# --- Immutability and basic behaviour -----------------------------------------------------------


def test_contracts_are_frozen() -> None:
    fact = PersonAt(LIN, STUDY, SlotIndex(0))
    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.person = ZHOU  # type: ignore[misc]


def test_localized_text_selects_language() -> None:
    text = LocalizedText(zh="书房", en="Study")
    assert text.get(Lang.ZH) == "书房"
    assert text.get(Lang.EN) == "Study"


def test_time_slot_label() -> None:
    assert TimeSlot(SlotIndex(0), 20 * 60, 20 * 60 + 15).label == "20:00–20:15"


def test_crime_window_is_strictly_between() -> None:
    report = CrimeReport(SEAL, STUDY, last_seen=SlotIndex(1), discovered=SlotIndex(4))
    assert report.window == (SlotIndex(2), SlotIndex(3))


def test_valid_view_and_case_build() -> None:
    view = _view()
    truth = Truth(culprit=ZHOU, timeline=(), item_timeline=(), events=(), knowledge=(), lies=())
    assert Case(view, truth).truth.culprit == ZHOU


# --- Validation ---------------------------------------------------------------------------------


def test_world_rejects_asymmetric_adjacency() -> None:
    with pytest.raises(ValueError, match="not symmetric"):
        World(
            people=(),
            locations=(_location(STUDY, CORRIDOR), _location(CORRIDOR)),
            slots=_slots(2),
            items=(),
        )


def test_world_rejects_unknown_item_owner() -> None:
    with pytest.raises(ValueError, match="unknown owner"):
        World(people=(), locations=(), slots=(), items=(Item(SEAL, _text("x"), owner=LIN),))


def test_crime_window_must_be_non_empty() -> None:
    with pytest.raises(ValueError, match="window"):
        CrimeReport(SEAL, STUDY, last_seen=SlotIndex(2), discovered=SlotIndex(3))


def test_case_rejects_culprit_outside_suspects() -> None:
    truth = Truth(culprit=CLIENT, timeline=(), item_timeline=(), events=(), knowledge=(), lies=())
    with pytest.raises(ValueError, match="suspects"):
        Case(_view(), truth)


def test_hearsay_needs_source() -> None:
    with pytest.raises(ValueError, match="hearsay"):
        Statement(LIN, PersonAt(ZHOU, LOBBY, SlotIndex(1)), Basis.HEARSAY)


def test_lie_must_be_exposable() -> None:
    lie = Statement(ZHOU, PersonAt(ZHOU, LOBBY, SlotIndex(2)), Basis.WITNESSED)
    with pytest.raises(ValueError, match="exposable"):
        Lie(lie, LieReason.ALIBI, exposed_by=())


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"kind": QueryKind.WHERE}, "needs 'slot'"),
        ({"kind": QueryKind.WHEN, "location": STUDY, "slot": SlotIndex(1)}, "must not set 'slot'"),
        ({"kind": QueryKind.SAW_PERSON, "person": LIN}, "saw themselves"),
        ({"kind": QueryKind.SMALL_TALK, "item": SEAL}, "must not set 'item'"),
    ],
)
def test_query_rejects_bad_shapes(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Query(addressee=LIN, **kwargs)


def test_query_accepts_optional_slot() -> None:
    query = Query(QueryKind.SAW_PERSON, addressee=LIN, person=ZHOU, slot=SlotIndex(2))
    assert query.slot == SlotIndex(2)


def test_allowed_facts_consistency() -> None:
    query = Query(QueryKind.WITH_WHOM, addressee=LIN, slot=SlotIndex(1))
    claim = Statement(LIN, Occupants(LOBBY, SlotIndex(1), frozenset({LIN})), Basis.WITNESSED)
    answer = AllowedFacts(speaker=LIN, query=query, stance=Stance.ANSWER, claims=(claim,))
    assert answer.claims == (claim,)

    with pytest.raises(ValueError, match="made by the speaker"):
        AllowedFacts(speaker=ZHOU, query=query, stance=Stance.ANSWER, claims=(claim,))
    with pytest.raises(ValueError, match="exactly when"):
        AllowedFacts(speaker=LIN, query=query, stance=Stance.DONT_KNOW, claims=(claim,))
    with pytest.raises(ValueError, match="CLARIFY"):
        AllowedFacts(speaker=LIN, query=None, stance=Stance.DEFLECT)
    assert AllowedFacts(speaker=LIN, query=None, stance=Stance.CLARIFY).claims == ()
