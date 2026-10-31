"""One game session: questions within a budget, the notebook, one accusation and a score.

This is the only module of the play loop that holds the truth. It answers through the answer
lookup and scores the accusation; the parser and the line writer receive `ParseRequest` and
`LineRequest` only (see `loosethread.npc`).

Fail closed: a parser that raises, or returns a query for someone else or with unknown names,
yields "please rephrase" at no cost. A writer that raises, returns nothing, or names anything its
facts do not authorise is replaced by the template line; the turn records why.
"""

from dataclasses import dataclass, field, replace
from enum import Enum

from loosethread.content import ContentPack, load_pack
from loosethread.difficulty import question_plan
from loosethread.lexicon import Lexicon
from loosethread.lines import template_line, unauthorised
from loosethread.lookup import AnswerBook
from loosethread.model import (
    AllowedFacts,
    Case,
    ItemAt,
    Lang,
    Occupants,
    PersonAt,
    PersonId,
    Query,
    Stance,
    Statement,
    Tone,
)
from loosethread.notebook import Notebook, effective_speaker
from loosethread.npc import (
    ClarifyReason,
    LineRequest,
    LineWriter,
    ParseRequest,
    ParseResult,
    QueryParser,
    Usage,
    tone_for,
)
from loosethread.solver import Solver

DEFAULT_BUDGET = 20  # CP-3, provisional until the P2 playtest
TWO_STARS_SHARE = 0.7  # DESIGN §9: two stars up to 70% of the budget


class GameOver(RuntimeError):
    """The accusation has been made, or there are no questions left to ask."""


class Outcome(Enum):
    SOLVED = "solved"  # right suspect, and the pair exposes one of their lies
    HUNCH = "hunch"  # right suspect, the pair does not
    WRONG = "wrong"


@dataclass(frozen=True)
class Turn:
    number: int
    addressee: PersonId
    question: str
    query: Query | None
    reason: ClarifyReason | None
    stance: Stance
    tone: Tone | None
    line: str
    cost: int
    repeat: bool
    new_notes: tuple[str, ...]
    new_conflicts: tuple[tuple[str, str], ...]
    problems: tuple[str, ...]  # why a backend result was rejected; empty when none was
    parse_usage: Usage
    line_usage: Usage


class AccusationError(ValueError):
    def __init__(self, key: str, detail: str = "") -> None:
        super().__init__(f"{key} {detail}".strip())
        self.key, self.detail = key, detail


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    stars: int  # 1-3 when solved, else 0
    accused: PersonId
    pair: tuple[str, str]
    exposes_lie: bool
    questions_used: int
    min_questions: int
    budget: int


@dataclass
class Game:
    case: Case
    parser: QueryParser
    writer: LineWriter
    lang: Lang = Lang.ZH
    budget: int = DEFAULT_BUDGET
    pack: ContentPack = field(default_factory=load_pack)
    used: int = 0
    turns: list[Turn] = field(default_factory=list)
    verdict: Verdict | None = None

    def __post_init__(self) -> None:
        view = self.case.view
        self.lexicon = Lexicon.build(view.world, view.crime, self.pack)
        self.notebook = Notebook(view)
        self._book = AnswerBook.from_truth(view.world, self.case.truth)
        self._asked: dict[PersonId, int] = {}
        self._queries: set[Query] = set()
        self._people = {p.id: p for p in view.world.people}

    @property
    def left(self) -> int:
        return self.budget - self.used

    # --- Questions -----------------------------------------------------------------------------

    def ask(self, addressee: PersonId, question: str) -> Turn:
        if self.verdict is not None or self.left <= 0:
            raise GameOver
        if addressee not in self._people:
            raise ValueError(f"unknown person {addressee!r}")
        problems: list[str] = []
        parsed, facts = self._understand(addressee, question, problems)
        query = parsed.query
        repeat = query is not None and query in self._queries
        request = LineRequest(
            self.lang, self._people[addressee], facts, self.case.view.world, parsed.reason, repeat
        )
        line, line_usage = self._write(request, problems)

        cost = 1 if query is not None and not repeat else 0
        before = set(self.notebook.conflicts())
        new_notes: tuple[str, ...] = ()
        if query is not None and cost:
            new_notes = self.notebook.record(query, facts.claims)
            self._queries.add(query)
            self._asked[addressee] = self._asked.get(addressee, 0) + 1
        self.used += cost
        turn = Turn(
            number=len(self.turns) + 1,
            addressee=addressee,
            question=question,
            query=query,
            reason=parsed.reason,
            stance=facts.stance,
            tone=facts.tone,
            line=line,
            cost=cost,
            repeat=repeat,
            new_notes=new_notes,
            new_conflicts=tuple(c for c in self.notebook.conflicts() if c not in before),
            problems=tuple(problems),
            parse_usage=parsed.usage,
            line_usage=line_usage,
        )
        self.turns.append(turn)
        return turn

    def _understand(
        self, addressee: PersonId, question: str, problems: list[str]
    ) -> tuple[ParseResult, AllowedFacts]:
        unclear = ParseResult(None, ClarifyReason.UNCLEAR)
        try:
            parsed = self.parser.parse(ParseRequest(question, addressee, self.lexicon))
        except Exception as exc:  # fail closed: any backend failure means "please rephrase"
            problems.append(f"parser_error:{type(exc).__name__}")
            parsed = unclear
        query = parsed.query
        if query is not None and query.addressee != addressee:
            problems.append("parser_wrong_addressee")
            parsed = replace(unclear, usage=parsed.usage)
        elif query is not None:
            try:
                answer = self._book.answer(query)
            except ValueError:
                problems.append("parser_unknown_name")
                parsed = replace(unclear, usage=parsed.usage)
            else:
                tone = tone_for(query, self._asked.get(addressee, 0))
                return parsed, replace(answer, tone=tone)
        return parsed, AllowedFacts(addressee, None, Stance.CLARIFY)

    def _write(self, request: LineRequest, problems: list[str]) -> tuple[str, Usage]:
        try:
            result = self.writer.write(request)
        except Exception as exc:  # fail closed: fall back to the template line
            problems.append(f"writer_error:{type(exc).__name__}")
            return template_line(request), Usage()
        bad = unauthorised(result.text, request, self.lexicon)
        if bad or not result.text.strip():
            problems.append("line_unauthorised:" + ",".join(bad) if bad else "line_empty")
            return template_line(request), result.usage
        return result.text.strip(), result.usage

    # --- Accusation ----------------------------------------------------------------------------

    def check_accusation(self, suspect: PersonId, first: str, second: str) -> tuple[str, str]:
        """Raise `AccusationError` if the accusation is malformed; return the normalised ids."""
        if self.verdict is not None:
            raise GameOver
        if suspect not in self.case.view.suspects:
            raise AccusationError("not_suspect", suspect)
        a, b = first.strip().upper(), second.strip().upper()
        for note_id in (a, b):
            if self.notebook.lookup(note_id) is None:
                raise AccusationError("unknown_item", note_id)
        if a == b:
            raise AccusationError("same_item", a)
        return a, b

    def accuse(self, suspect: PersonId, first: str, second: str) -> Verdict:
        """One accusation per game: a suspect plus two notebook items that cannot both be true."""
        a, b = self.check_accusation(suspect, first, second)
        view = self.case.view
        exposes = self._exposes_culprit_lie(a, b)
        culprit = self.case.truth.culprit
        min_q = len(question_plan(view, Solver(view))[0])
        stars = 0
        if suspect != culprit:
            outcome = Outcome.WRONG
        elif not exposes:
            outcome = Outcome.HUNCH
        else:
            outcome = Outcome.SOLVED
            if self.used <= min_q + 2:
                stars = 3
            elif self.used <= int(TWO_STARS_SHARE * self.budget):
                stars = 2
            else:
                stars = 1
        self.verdict = Verdict(
            outcome, stars, suspect, (a, b), exposes, self.used, min_q, self.budget
        )
        return self.verdict

    def exposing_pairs(self) -> tuple[tuple[str, str], ...]:
        """After the accusation: the notebook pairs that would have exposed the culprit's lie."""
        if self.verdict is None:
            raise RuntimeError("the answer is shown only after the accusation")
        return tuple(p for p in self.notebook.conflicts() if self._exposes_culprit_lie(*p))

    def _exposes_culprit_lie(self, a: str, b: str) -> bool:
        """The pair conflicts, and one side is a false claim whose source is the culprit."""
        if not self.notebook.in_conflict(a, b):
            return False
        culprit = self.case.truth.culprit
        for note_id in (a, b):
            item = self.notebook.lookup(note_id)
            if (
                isinstance(item, Statement)
                and effective_speaker(item) == culprit
                and self._false(item)
            ):
                return True
        return False

    def _false(self, s: Statement) -> bool:
        truth = self.case.truth
        where = {(f.person, int(f.slot)): f.location for f in truth.timeline}
        match s.claim:
            case PersonAt(person, location, slot):
                return where[(person, int(slot))] != location
            case Occupants(location, slot, people):
                there = {p for (p, t), loc in where.items() if t == slot and loc == location}
                return there != people
            case ItemAt(item, location, slot):
                places = {(f.item, int(f.slot)): f.location for f in truth.item_timeline}
                return places.get((item, int(slot))) != location
