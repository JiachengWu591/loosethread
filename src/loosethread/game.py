"""One game session: questions within a budget, the notebook, one accusation and a score.

This is the only module of the play loop that holds the truth. It answers through the answer
lookup and scores the accusation; the parser and the line writer receive `ParseRequest` and
`LineRequest` only (see `loosethread.npc`).

Fail closed: a parser that raises, or returns a query for someone else or with unknown names,
yields "please rephrase" at no cost. A parser model that cannot be reached yields a free "ask
again" that says so, without calling the writer. A writer that raises, returns nothing, or names
anything its facts do not authorise is replaced by the template line; the turn records why.

Three rules of the session itself (D-029): "where were you" is answered as "where, and with whom";
an answer with no case facts is free; a question that needs a time and names none takes the time
just discussed, when it has no relative word.
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
    QueryKind,
    SlotIndex,
    Stance,
    Statement,
    Tone,
)
from loosethread.notebook import Notebook, effective_speaker
from loosethread.npc import (
    BackendError,
    BackendUnavailable,
    ClarifyReason,
    LineRequest,
    LineWriter,
    ParseRequest,
    ParseResult,
    QueryParser,
    Usage,
    tone_for,
)
from loosethread.parser import follows_up
from loosethread.solver import Solver

# CP-6 (D-027): below the 15-question sweep of every daily case; provisional until the next
# playtest. CP-3 had 20.
DEFAULT_BUDGET = 12
# Answers that state no case facts cost nothing (D-029; DESIGN §11 item 3 charged them).
_NO_FACTS = frozenset({QueryKind.OPINION, QueryKind.SMALL_TALK, QueryKind.OUT_OF_SCOPE})


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
class StarRule:
    """Most questions for each star in one case (CP-5, DESIGN §9).

    Set by simulated systematic players (`loosethread.simulate`): ★★★ up to the fastest quarter of
    them, ★★ up to their median, both capped at the budget.
    """

    three: int
    two: int

    def __post_init__(self) -> None:
        if not 0 < self.three <= self.two:
            raise ValueError("star thresholds must satisfy 0 < three <= two")

    def stars(self, used: int) -> int:
        return 3 if used <= self.three else 2 if used <= self.two else 1


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
    star_rule: StarRule


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
    stars: StarRule | None = None  # computed on first use when not given

    def __post_init__(self) -> None:
        view = self.case.view
        self.lexicon = Lexicon.build(view.world, view.crime, self.pack)
        self.notebook = Notebook(view)
        self._book = AnswerBook.from_truth(view.world, self.case.truth)
        self._asked: dict[PersonId, int] = {}
        self._queries: set[Query] = set()
        self._people = {p.id: p for p in view.world.people}
        self._last_slot: SlotIndex | None = None  # the time just discussed, with anyone

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
        if parsed.reason is ClarifyReason.UNAVAILABLE:  # the writer is most likely unreachable too
            line, line_usage = template_line(request), Usage()
        else:
            line, line_usage = self._write(request, problems)

        cost = 1 if query is not None and not repeat and query.kind not in _NO_FACTS else 0
        if query is not None and query.slot is not None:
            self._last_slot = query.slot
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

    def _read(self, addressee: PersonId, question: str, problems: list[str]) -> ParseResult:
        try:
            return self.parser.parse(ParseRequest(question, addressee, self.lexicon))
        except BackendUnavailable as exc:
            problems.append(f"parser_unavailable:{exc.cause}")
            return ParseResult(None, ClarifyReason.UNAVAILABLE)
        except BackendError as exc:
            problems.append(f"parser_invalid:{exc.detail}")
            return ParseResult(None, ClarifyReason.UNCLEAR, exc.usage)
        except Exception as exc:  # fail closed: any backend failure means "please rephrase"
            problems.append(f"parser_error:{type(exc).__name__}")
            return ParseResult(None, ClarifyReason.UNCLEAR)

    def _with_last_slot(
        self, addressee: PersonId, question: str, first: ParseResult, problems: list[str]
    ) -> ParseResult:
        """Read a question that named no time again, at the time just discussed; a second model
        call, and the prompt's rules stay as they are. Keeps "which time?" if that reads no better.
        """
        assert self._last_slot is not None
        start = self.case.view.world.slots[self._last_slot].label.split("–")[0]
        again = self._read(addressee, f"{start} {question}", problems)
        usage = first.usage + again.usage
        if again.reason is ClarifyReason.UNAVAILABLE:
            return replace(again, usage=usage)
        if again.query is None or again.query.slot != self._last_slot:
            return replace(first, usage=usage)
        return replace(again, usage=usage)

    def _understand(
        self, addressee: PersonId, question: str, problems: list[str]
    ) -> tuple[ParseResult, AllowedFacts]:
        unclear = ParseResult(None, ClarifyReason.UNCLEAR)
        parsed = self._read(addressee, question, problems)
        if (
            parsed.reason is ClarifyReason.NEED_TIME
            and self._last_slot is not None
            and follows_up(question, self.lexicon)
        ):
            parsed = self._with_last_slot(addressee, question, parsed, problems)
        query = parsed.query
        if query is not None and query.kind is QueryKind.WHERE:
            # The usual contradiction needs the company, and "where" is what players ask first:
            # half of the questions in two AI playtests (D-028).
            query = replace(query, kind=QueryKind.WITH_WHOM)
            parsed = replace(parsed, query=query)
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
        except BackendUnavailable as exc:
            problems.append(f"writer_unavailable:{exc.cause}")
            return template_line(request), Usage()
        except BackendError as exc:
            problems.append(f"writer_invalid:{exc.detail}")
            return template_line(request), exc.usage
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
        exposes = self.exposes_culprit_lie(a, b)
        culprit = self.case.truth.culprit
        min_q = len(question_plan(view, Solver(view))[0])
        rule = self.star_rule()
        stars = 0
        if suspect != culprit:
            outcome = Outcome.WRONG
        elif not exposes:
            outcome = Outcome.HUNCH
        else:
            outcome = Outcome.SOLVED
            stars = rule.stars(self.used)
        self.verdict = Verdict(
            outcome, stars, suspect, (a, b), exposes, self.used, min_q, self.budget, rule
        )
        return self.verdict

    def star_rule(self) -> StarRule:
        """This case's star thresholds (CP-5); simulated once, on first use, about a second."""
        if self.stars is None:
            # `simulate` plays whole games itself, so it is imported here, not at the top.
            from loosethread.simulate import star_rule  # noqa: PLC0415

            self.stars = star_rule(self.case, self.budget)
        return self.stars

    def exposing_pairs(self) -> tuple[tuple[str, str], ...]:
        """After the accusation: the notebook pairs that would have exposed the culprit's lie."""
        if self.verdict is None:
            raise RuntimeError("the answer is shown only after the accusation")
        return tuple(p for p in self.notebook.conflicts() if self.exposes_culprit_lie(*p))

    def exposes_culprit_lie(self, a: str, b: str) -> bool:
        """The pair conflicts, and one side is a false claim whose source is the culprit.

        Reads the truth: used to score accusations and by the simulated player. The terminal
        front end reaches it only through `exposing_pairs`, after the accusation.
        """
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
