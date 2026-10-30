"""Answer lookup: from what an NPC knows plus the case's lies to the facts one answer may state.

This is the only code that turns truth into speech. It reads `Knowledge` and lie claims and emits
`AllowedFacts`, which carry claims but no marker of which are lies. The same query always gets the
same answer.

Answer rules (DESIGN.md §5, §7):
- a person's claimed location is the true one, except at their lie slots;
- at a lie slot the liar claims to have been alone at the claimed location;
- at other slots a person reports exactly who shared their location (W3);
- sightings of the item or of others are only reported for slots where the speaker tells the truth;
- hearsay is repeated as told, with its source.
"""

from collections.abc import Iterable
from typing import Self

from loosethread.model import (
    AllowedFacts,
    Basis,
    ItemAt,
    Knowledge,
    LocationId,
    Occupants,
    PersonAt,
    PersonId,
    Query,
    QueryKind,
    SlotIndex,
    Stance,
    Statement,
    Testimony,
    Truth,
    World,
)


class AnswerBook:
    def __init__(
        self, world: World, knowledge: Iterable[Knowledge], lies: Iterable[Statement]
    ) -> None:
        self.world = world
        self._people = frozenset(p.id for p in world.people)
        self._locations = frozenset(loc.id for loc in world.locations)
        self._items = frozenset(i.id for i in world.items)
        self._n_slots = len(world.slots)

        self._location: dict[tuple[PersonId, int], LocationId] = {}
        self._occupants: dict[tuple[PersonId, int], frozenset[PersonId]] = {}
        self._sightings: dict[PersonId, list[ItemAt]] = {}
        self._hearsay: dict[PersonId, list[tuple[PersonAt, PersonId]]] = {}
        for k in knowledge:
            match k.fact:
                case PersonAt(person, location, slot) if k.basis is Basis.WITNESSED:
                    if person == k.holder:
                        self._location[(person, slot)] = location
                case PersonAt() as fact if k.source is not None:
                    self._hearsay.setdefault(k.holder, []).append((fact, k.source))
                case Occupants(_, slot, people):
                    self._occupants[(k.holder, slot)] = people
                case ItemAt() as fact:
                    self._sightings.setdefault(k.holder, []).append(fact)
                case _:
                    raise ValueError(f"unsupported knowledge: {k!r}")

        self._lie_at: dict[tuple[PersonId, int], LocationId] = {}
        for lie in lies:
            claim = lie.claim
            if not isinstance(claim, PersonAt) or claim.person != lie.speaker:
                raise ValueError("lies are claims about the liar's own location")
            self._lie_at[(lie.speaker, claim.slot)] = claim.location

        for person in self._people:
            for t in range(self._n_slots):
                if (person, t) not in self._location or (person, t) not in self._occupants:
                    raise ValueError(f"knowledge of {person!r} is missing slot {t}")

    @classmethod
    def from_truth(cls, world: World, truth: Truth) -> Self:
        return cls(world, truth.knowledge, (lie.statement for lie in truth.lies))

    # --- What a person claims ----------------------------------------------------------------

    def claimed_location(self, person: PersonId, slot: int) -> LocationId:
        return self._lie_at.get((person, slot), self._location[(person, slot)])

    def _lies_at(self, person: PersonId, slot: int) -> bool:
        return (person, slot) in self._lie_at

    def _own(self, person: PersonId, slot: int) -> Statement:
        where = self.claimed_location(person, slot)
        return Statement(person, PersonAt(person, where, SlotIndex(slot)), Basis.WITNESSED)

    def _company(self, person: PersonId, slot: int) -> Statement:
        where = self.claimed_location(person, slot)
        people = (
            frozenset({person}) if self._lies_at(person, slot) else self._occupants[(person, slot)]
        )
        return Statement(person, Occupants(where, SlotIndex(slot), people), Basis.WITNESSED)

    # --- Answers -------------------------------------------------------------------------------

    def answer(self, query: Query) -> AllowedFacts:
        self._check(query)
        p = query.addressee
        claims: tuple[Statement, ...]
        match query.kind:
            case QueryKind.WHERE:
                claims = (self._own(p, _req(query.slot)),)
            case QueryKind.WHEN:
                claims = tuple(
                    self._own(p, t)
                    for t in range(self._n_slots)
                    if self.claimed_location(p, t) == query.location
                )
            case QueryKind.WITH_WHOM:
                claims = (self._company(p, _req(query.slot)),)
            case QueryKind.SAW_PERSON if query.slot is not None:
                claims = (self._company(p, query.slot),)
            case QueryKind.SAW_PERSON:
                claims = self._sightings_of(p, _req(query.person))
            case QueryKind.ABOUT_ITEM:
                claims = tuple(
                    Statement(p, fact, Basis.WITNESSED)
                    for fact in self._sightings.get(p, [])
                    if fact.item == query.item and not self._lies_at(p, fact.slot)
                )
            case QueryKind.OPINION | QueryKind.SMALL_TALK | QueryKind.OUT_OF_SCOPE:
                return AllowedFacts(speaker=p, query=query, stance=Stance.DEFLECT)
        stance = Stance.ANSWER if claims else Stance.DENY
        return AllowedFacts(speaker=p, query=query, stance=stance, claims=claims)

    def _sightings_of(self, speaker: PersonId, other: PersonId) -> tuple[Statement, ...]:
        seen = [
            Statement(
                speaker,
                PersonAt(other, self.claimed_location(speaker, t), SlotIndex(t)),
                Basis.WITNESSED,
            )
            for t in range(self._n_slots)
            if not self._lies_at(speaker, t) and other in self._occupants[(speaker, t)]
        ]
        heard = [
            Statement(speaker, fact, Basis.HEARSAY, source=source)
            for fact, source in self._hearsay.get(speaker, [])
            if fact.person == other
        ]
        return (*seen, *heard)

    def _check(self, query: Query) -> None:
        if query.addressee not in self._people:
            raise ValueError(f"unknown addressee {query.addressee!r}")
        if query.person is not None and query.person not in self._people:
            raise ValueError(f"unknown person {query.person!r}")
        if query.location is not None and query.location not in self._locations:
            raise ValueError(f"unknown location {query.location!r}")
        if query.item is not None and query.item not in self._items:
            raise ValueError(f"unknown item {query.item!r}")
        if query.slot is not None and not 0 <= query.slot < self._n_slots:
            raise ValueError(f"slot {query.slot} is outside the evening")

    def testimony(self) -> tuple[Testimony, ...]:
        """Answers with claims for every in-scope query, in a fixed order."""
        entries = []
        for query in in_scope_queries(self.world):
            answer = self.answer(query)
            if answer.claims:
                entries.append(Testimony(query, answer.claims))
        return tuple(entries)


def in_scope_queries(world: World) -> tuple[Query, ...]:
    """Every factual query the game supports, per person, in a fixed order."""
    queries: list[Query] = []
    slots = [s.index for s in world.slots]
    for person in world.people:
        p = person.id
        queries += [Query(QueryKind.WHERE, p, slot=t) for t in slots]
        queries += [Query(QueryKind.WHEN, p, location=loc.id) for loc in world.locations]
        queries += [Query(QueryKind.WITH_WHOM, p, slot=t) for t in slots]
        for other in world.people:
            if other.id == p:
                continue
            queries.append(Query(QueryKind.SAW_PERSON, p, person=other.id))
            queries += [Query(QueryKind.SAW_PERSON, p, person=other.id, slot=t) for t in slots]
        queries += [Query(QueryKind.ABOUT_ITEM, p, item=i.id) for i in world.items]
    return tuple(queries)


def _req[T](value: T | None) -> T:
    if value is None:  # unreachable: Query validation guarantees required fields
        raise ValueError("query is missing a required field")
    return value
