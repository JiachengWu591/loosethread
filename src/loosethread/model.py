"""Data contracts for the world model, the player's view and the NPC pipeline (first draft).

Three groups of types:

- public: what the player can learn (`World`, `Evidence`, `Statement`, `PlayerView`, ...);
- truth: what only the generator and the answer lookup may read (`Truth`, `Lie`, `Knowledge`,
  `Event`);
- pipeline: `Query` (parser output) and `AllowedFacts` (the only case input a line LLM may receive).

No truth type may be reachable from `PlayerView` or `AllowedFacts`; `tests/test_model.py` checks
this by walking the type annotations.
"""

from dataclasses import dataclass
from enum import Enum
from itertools import pairwise
from typing import NewType

PersonId = NewType("PersonId", str)
LocationId = NewType("LocationId", str)
ItemId = NewType("ItemId", str)
EvidenceId = NewType("EvidenceId", str)
SlotIndex = NewType("SlotIndex", int)

MINUTES_PER_DAY = 24 * 60


class Lang(Enum):
    ZH = "zh"
    EN = "en"


@dataclass(frozen=True)
class LocalizedText:
    zh: str
    en: str

    def get(self, lang: Lang) -> str:
        return self.zh if lang is Lang.ZH else self.en


# --- Public world ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Person:
    id: PersonId
    name: LocalizedText
    role: LocalizedText
    # Voice and manner notes for the line LLM. Never contains case facts.
    persona: LocalizedText


@dataclass(frozen=True)
class Location:
    id: LocationId
    name: LocalizedText
    neighbors: frozenset[LocationId]

    def __post_init__(self) -> None:
        if self.id in self.neighbors:
            raise ValueError(f"location {self.id!r} lists itself as a neighbor")


@dataclass(frozen=True)
class TimeSlot:
    index: SlotIndex
    start_minute: int  # minutes after midnight
    end_minute: int

    def __post_init__(self) -> None:
        if not 0 <= self.start_minute < self.end_minute <= MINUTES_PER_DAY:
            raise ValueError(f"invalid time slot {self.start_minute}-{self.end_minute}")

    @property
    def label(self) -> str:
        return f"{_clock(self.start_minute)}–{_clock(self.end_minute)}"


def _clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


@dataclass(frozen=True)
class Item:
    id: ItemId
    name: LocalizedText
    owner: PersonId | None


@dataclass(frozen=True)
class Motive:
    """A public, plausible reason to steal. Every suspect has one, so motive never decides alone."""

    person: PersonId
    reason: LocalizedText


@dataclass(frozen=True)
class World:
    people: tuple[Person, ...]
    locations: tuple[Location, ...]
    slots: tuple[TimeSlot, ...]
    items: tuple[Item, ...]

    def __post_init__(self) -> None:
        person_ids = [p.id for p in self.people]
        location_ids = [loc.id for loc in self.locations]
        item_ids = [i.id for i in self.items]
        for kind, ids in (("person", person_ids), ("location", location_ids), ("item", item_ids)):
            if len(set(ids)) != len(ids):
                raise ValueError(f"duplicate {kind} ids")
        by_id = {loc.id: loc for loc in self.locations}
        for loc in self.locations:
            for other in loc.neighbors:
                if other not in by_id:
                    raise ValueError(f"{loc.id!r} has unknown neighbor {other!r}")
                if loc.id not in by_id[other].neighbors:
                    raise ValueError(f"adjacency {loc.id!r}-{other!r} is not symmetric")
        for expected, slot in enumerate(self.slots):
            if slot.index != expected:
                raise ValueError("slot indices must be 0..n-1 in order")
        for earlier, later in pairwise(self.slots):
            if earlier.end_minute > later.start_minute:
                raise ValueError("time slots overlap or are out of order")
        for item in self.items:
            if item.owner is not None and item.owner not in person_ids:
                raise ValueError(f"item {item.id!r} has unknown owner {item.owner!r}")


# --- Facts: atomic claims about the world ------------------------------------------------------


@dataclass(frozen=True)
class PersonAt:
    """`person` spent time slot `slot` at `location`."""

    person: PersonId
    location: LocationId
    slot: SlotIndex


@dataclass(frozen=True)
class Occupants:
    """Exactly `people` were at `location` during `slot` (as seen by someone who was there)."""

    location: LocationId
    slot: SlotIndex
    people: frozenset[PersonId]


@dataclass(frozen=True)
class ItemAt:
    """`item` was at `location` during `slot`."""

    item: ItemId
    location: LocationId
    slot: SlotIndex


type Fact = PersonAt | Occupants | ItemAt


class Basis(Enum):
    WITNESSED = "witnessed"
    HEARSAY = "hearsay"


@dataclass(frozen=True)
class Statement:
    """A claim a person makes when asked. It may be false; by design it carries no truth flag."""

    speaker: PersonId
    claim: Fact
    basis: Basis
    source: PersonId | None = None  # who told the speaker, for hearsay

    def __post_init__(self) -> None:
        if (self.basis is Basis.HEARSAY) != (self.source is not None):
            raise ValueError("hearsay statements need a source; witnessed ones must not have one")


class EvidenceKind(Enum):
    RECORD = "record"
    PHOTO = "photo"
    PHYSICAL = "physical"


@dataclass(frozen=True)
class Evidence:
    """Always true. `establishes` lists the facts it proves; `text` is how it is shown."""

    id: EvidenceId
    kind: EvidenceKind
    establishes: tuple[Fact, ...]
    text: LocalizedText

    def __post_init__(self) -> None:
        if not self.establishes:
            raise ValueError(f"evidence {self.id!r} establishes nothing")


@dataclass(frozen=True)
class CrimeReport:
    """Public facts about the theft. The theft happened strictly between the two slots."""

    item: ItemId
    location: LocationId
    last_seen: SlotIndex
    discovered: SlotIndex

    def __post_init__(self) -> None:
        if self.discovered - self.last_seen < 2:
            raise ValueError("theft window must contain at least one slot")

    @property
    def window(self) -> tuple[SlotIndex, ...]:
        return tuple(SlotIndex(s) for s in range(self.last_seen + 1, self.discovered))


@dataclass(frozen=True)
class PlayerView:
    """Everything the player can learn. The solver's only input.

    `testimony` holds the answer to every in-scope query that yields claims; the player obtains
    each one by asking. Answers are fixed at generation time.
    """

    seed: int
    world: World
    suspects: frozenset[PersonId]
    motives: tuple[Motive, ...]
    crime: CrimeReport
    evidence: tuple[Evidence, ...]
    testimony: tuple["Testimony", ...]
    pack_id: str = "mistpine"  # the content pack: its setting, story, map and name aliases

    def __post_init__(self) -> None:
        person_ids = {p.id for p in self.world.people}
        if not self.suspects <= person_ids:
            raise ValueError("every suspect must be a person in the world")
        if any(t.query.addressee not in person_ids for t in self.testimony):
            raise ValueError("testimony from someone who is not in the world")
        if self.crime.item not in {i.id for i in self.world.items}:
            raise ValueError("crime report names an unknown item")
        if self.crime.location not in {loc.id for loc in self.world.locations}:
            raise ValueError("crime report names an unknown location")
        if self.crime.discovered >= len(self.world.slots):
            raise ValueError("crime report refers to a slot outside the evening")

    @property
    def statements(self) -> tuple[Statement, ...]:
        """Every distinct claim in the testimony, in first-seen order."""
        return tuple(dict.fromkeys(c for t in self.testimony for c in t.claims))


# --- Truth: never reachable from PlayerView or AllowedFacts ------------------------------------


class EventKind(Enum):
    THEFT = "theft"


@dataclass(frozen=True)
class Event:
    kind: EventKind
    actor: PersonId
    item: ItemId
    location: LocationId
    slot: SlotIndex


@dataclass(frozen=True)
class Knowledge:
    """What one NPC actually knows and how they came to know it."""

    holder: PersonId
    fact: Fact
    basis: Basis
    source: PersonId | None = None


class LieReason(Enum):
    ALIBI = "alibi"  # the culprit covering the theft
    PRIVACY = "privacy"  # an innocent hiding something unrelated


@dataclass(frozen=True)
class Lie:
    statement: Statement
    reason: LieReason
    exposed_by: tuple[EvidenceId | Statement, ...]

    def __post_init__(self) -> None:
        if not self.exposed_by:
            raise ValueError("every lie must be exposable by evidence or testimony")


@dataclass(frozen=True)
class Truth:
    culprit: PersonId
    timeline: tuple[PersonAt, ...]  # one entry per (person, slot)
    item_timeline: tuple[ItemAt, ...]
    events: tuple[Event, ...]
    knowledge: tuple[Knowledge, ...]
    lies: tuple[Lie, ...]


@dataclass(frozen=True)
class Case:
    view: PlayerView
    truth: Truth

    def __post_init__(self) -> None:
        if self.truth.culprit not in self.view.suspects:
            raise ValueError("the culprit must be one of the suspects")


# --- Pipeline ---------------------------------------------------------------------------------


class QueryKind(Enum):
    WHERE = "where"  # where were you during <slot>?
    WHEN = "when"  # when were you at <location>?
    WITH_WHOM = "with_whom"  # who was with you during <slot>?
    SAW_PERSON = "saw_person"  # did you see <person> (during <slot>)?
    ABOUT_ITEM = "about_item"  # what do you know about <item>?
    OPINION = "opinion"  # what do you think of <person>?
    SMALL_TALK = "small_talk"
    OUT_OF_SCOPE = "out_of_scope"


_QUERY_SLOTS = ("slot", "location", "person", "item")
# kind -> (required fields, optional fields)
_QUERY_FIELDS: dict[QueryKind, tuple[frozenset[str], frozenset[str]]] = {
    QueryKind.WHERE: (frozenset({"slot"}), frozenset()),
    QueryKind.WHEN: (frozenset({"location"}), frozenset()),
    QueryKind.WITH_WHOM: (frozenset({"slot"}), frozenset()),
    QueryKind.SAW_PERSON: (frozenset({"person"}), frozenset({"slot"})),
    QueryKind.ABOUT_ITEM: (frozenset({"item"}), frozenset()),
    QueryKind.OPINION: (frozenset({"person"}), frozenset()),
    QueryKind.SMALL_TALK: (frozenset(), frozenset()),
    QueryKind.OUT_OF_SCOPE: (frozenset(), frozenset()),
}


def query_fields(kind: QueryKind) -> frozenset[str]:
    """The fields a query of this kind may set, required or optional."""
    required, optional = _QUERY_FIELDS[kind]
    return required | optional


@dataclass(frozen=True)
class Query:
    """Structured form of one player question, produced by the parser. Invalid shapes raise."""

    kind: QueryKind
    addressee: PersonId
    slot: SlotIndex | None = None
    location: LocationId | None = None
    person: PersonId | None = None
    item: ItemId | None = None

    def __post_init__(self) -> None:
        required, optional = _QUERY_FIELDS[self.kind]
        for name in _QUERY_SLOTS:
            present = getattr(self, name) is not None
            if name in required and not present:
                raise ValueError(f"{self.kind.value} query needs {name!r}")
            if present and name not in required | optional:
                raise ValueError(f"{self.kind.value} query must not set {name!r}")
        if self.kind is QueryKind.SAW_PERSON and self.person == self.addressee:
            raise ValueError("cannot ask someone whether they saw themselves")


class Stance(Enum):
    ANSWER = "answer"  # states the claims
    DENY = "deny"  # rejects the premise: was never there, never saw them or it
    DONT_KNOW = "dont_know"  # honestly has nothing to say
    DEFLECT = "deflect"  # small talk, opinion or out of scope: no case facts
    CLARIFY = "clarify"  # the question could not be parsed; ask the player to rephrase


class Tone(Enum):
    CALM = "calm"
    NERVOUS = "nervous"
    EVASIVE = "evasive"
    IRRITATED = "irritated"


@dataclass(frozen=True)
class AllowedFacts:
    """The only case information a line LLM may receive for one answer.

    Claims may be true or lies; nothing marks which. Built by the lookup + lie policy from `Truth`,
    but holds no reference to it.
    """

    speaker: PersonId
    query: Query | None  # None when the question could not be parsed
    stance: Stance
    claims: tuple[Statement, ...] = ()
    tone: Tone | None = None

    def __post_init__(self) -> None:
        if any(c.speaker != self.speaker for c in self.claims):
            raise ValueError("all claims must be made by the speaker")
        if (self.stance is Stance.ANSWER) != bool(self.claims):
            raise ValueError("claims are given exactly when the stance is ANSWER")
        if (self.query is None) != (self.stance is Stance.CLARIFY):
            raise ValueError("only a CLARIFY answer has no parsed query")
        if self.query is not None and self.query.addressee != self.speaker:
            raise ValueError("the speaker must be the person the query was addressed to")


@dataclass(frozen=True)
class Testimony:
    """The claims `query.addressee` makes when asked `query`. Fixed at generation time."""

    query: Query
    claims: tuple[Statement, ...]

    def __post_init__(self) -> None:
        if not self.claims:
            raise ValueError("testimony without claims is not recorded")
        if any(c.speaker != self.query.addressee for c in self.claims):
            raise ValueError("all claims must be made by the person asked")
