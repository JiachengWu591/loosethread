"""Contracts between the game and its language backends: the question parser and the line writer.

Isolation (DESIGN §7, ROADMAP P2): a parser sees names and the raw question, nothing else; a line
writer sees the speaker's public card, `AllowedFacts`, display names and flags. No field of either
request can reach a truth type (`tests/test_model.py` walks the annotations). Backends that call a
language model build their prompts from these requests only.

The tone tag is derived from public information only: the kind of question and how often this
person has been asked. It never depends on who is guilty or whether a claim is a lie; a culprit who
"sounds nervous" would give the answer away without any contradiction.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from loosethread.lexicon import Lexicon
from loosethread.model import AllowedFacts, Lang, Person, PersonId, Query, QueryKind, Tone, World


@dataclass(frozen=True)
class Usage:
    """Cost of backend calls. Zero for the offline template backend."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.calls + other.calls,
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
            self.seconds + other.seconds,
        )


class ClarifyReason(Enum):
    UNCLEAR = "unclear"  # no question shape recognised
    NEED_TIME = "need_time"  # the question needs a time and has none
    BAD_TIME = "bad_time"  # the time is outside the evening
    TWO_PEOPLE = "two_people"  # more than one other person named


@dataclass(frozen=True)
class ParseRequest:
    question: str
    addressee: PersonId
    lexicon: Lexicon


@dataclass(frozen=True)
class ParseResult:
    query: Query | None
    reason: ClarifyReason | None = None
    usage: Usage = Usage()

    def __post_init__(self) -> None:
        if (self.query is None) == (self.reason is None):
            raise ValueError("a parse yields either a query or a reason to clarify")


class QueryParser(Protocol):
    def parse(self, request: ParseRequest) -> ParseResult: ...


@dataclass(frozen=True)
class LineRequest:
    lang: Lang
    speaker: Person
    facts: AllowedFacts
    world: World  # public display names for the ids in `facts`
    reason: ClarifyReason | None = None  # set exactly when the stance is CLARIFY
    repeat: bool = False  # the same query was asked before; the answer is the same

    def __post_init__(self) -> None:
        if self.speaker.id != self.facts.speaker:
            raise ValueError("the speaker card must match the facts")
        if (self.reason is None) != (self.facts.query is not None):
            raise ValueError("a clarify reason is given exactly when there is no query")


@dataclass(frozen=True)
class LineResult:
    text: str
    usage: Usage = Usage()


class LineWriter(Protocol):
    def write(self, request: LineRequest) -> LineResult: ...


IRRITATED_AFTER = 5  # questions already put to the same person


def tone_for(query: Query, asked_before: int) -> Tone:
    """Tone from public information only (see the module docstring)."""
    if query.kind is QueryKind.OUT_OF_SCOPE:
        return Tone.EVASIVE
    if asked_before >= IRRITATED_AFTER:
        return Tone.IRRITATED
    return Tone.CALM
