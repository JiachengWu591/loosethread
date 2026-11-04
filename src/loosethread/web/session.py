"""One game as data for a page: a `Game`, its state in the player's language, and a save.

The state holds what the player may see. `Ending`, which carries the truth, exists only after the
accusation. The save lets a game survive a refresh with no further model call: it records how each
question was read and what was said, and `WebSession` replays that through the same `Game`. It holds
the player's questions and the lines, and neither the truth nor any key.

A save that cannot be read or replayed is dropped and the game starts afresh, with a notice. It is
never trusted to score anything: replaying asks the `Game`, which holds the truth, again.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from loosethread import __version__
from loosethread.case import Grid, Sheet, TruthParts, notebook_grid, sheet_parts, truth_parts
from loosethread.game import AccusationError, Game, GameOver, Turn
from loosethread.generator import daily_case
from loosethread.lines import TemplateWriter
from loosethread.llm.chat import ChatModel
from loosethread.llm.config import load_backends
from loosethread.llm.parser import LLMParser
from loosethread.llm.writer import LLMWriter
from loosethread.model import (
    Evidence,
    ItemId,
    Lang,
    LocationId,
    PersonId,
    Query,
    QueryKind,
    SlotIndex,
    Stance,
)
from loosethread.notebook import describe
from loosethread.npc import (
    BackendUnavailable,
    ClarifyReason,
    LineRequest,
    LineResult,
    LineWriter,
    ParseRequest,
    ParseResult,
    QueryParser,
    Usage,
)
from loosethread.parser import RuleParser
from loosethread.play import addressee_of, conflict_text, ending_lines, problem_text, status_of
from loosethread.web.share import mark, share_card

BACKEND = "deepseek"  # the one a player's key is for
SAVE_VERSION = 1
MAX_QUESTION = 200  # characters; a question this long is not one, and a model charges for it


@dataclass(frozen=True)
class SavedParse:
    """One reading of a question: a query, or the reason there was none."""

    kind: str = ""
    addressee: str = ""
    slot: int | None = None
    location: str | None = None
    person: str | None = None
    item: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class SavedTurn:
    addressee: str
    question: str
    lang: str
    parses: tuple[SavedParse, ...]
    line: str


@dataclass(frozen=True)
class SavedAccusation:
    suspect: str
    first: str
    second: str


@dataclass(frozen=True)
class SavedGame:
    version: int
    seed: int
    prompt_tokens: int
    completion_tokens: int
    turns: tuple[SavedTurn, ...]
    accusation: SavedAccusation | None
    hints: bool = True


def _save_parse(result: ParseResult) -> SavedParse:
    query = result.query
    if query is None:
        assert result.reason is not None  # guaranteed by ParseResult validation
        return SavedParse(reason=result.reason.value)
    return SavedParse(
        query.kind.value,
        query.addressee,
        None if query.slot is None else int(query.slot),
        query.location,
        query.person,
        query.item,
    )


def _load_parse(saved: SavedParse) -> ParseResult:
    if saved.reason:
        return ParseResult(None, ClarifyReason(saved.reason))
    return ParseResult(
        Query(
            QueryKind(saved.kind),
            PersonId(saved.addressee),
            None if saved.slot is None else SlotIndex(saved.slot),
            None if saved.location is None else LocationId(saved.location),
            None if saved.person is None else PersonId(saved.person),
            None if saved.item is None else ItemId(saved.item),
        )
    )


def read_save(text: str, seed: int) -> SavedGame | None:
    """The save in `text` if it is whole and for this case; otherwise None."""
    try:
        raw = json.loads(text)
        accused = raw["accusation"]
        saved = SavedGame(
            int(raw["version"]),
            int(raw["seed"]),
            int(raw["prompt_tokens"]),
            int(raw["completion_tokens"]),
            tuple(
                SavedTurn(
                    str(t["addressee"]),
                    str(t["question"]),
                    str(t["lang"]),
                    tuple(SavedParse(**p) for p in t["parses"]),
                    str(t["line"]),
                )
                for t in raw["turns"]
            ),
            SavedAccusation(**accused) if accused is not None else None,
            bool(raw.get("hints", True)),  # a save from before hard mode had hints
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return saved if saved.version == SAVE_VERSION and saved.seed == seed else None


class _Recording:
    """Keeps what the current parser returned this turn. A failure is kept as what `Game` makes of
    it: unreachable stays unreachable, and any other failure means "please rephrase"."""

    def __init__(self, inner: QueryParser) -> None:
        self.inner = inner
        self.parses: list[SavedParse] = []

    def parse(self, request: ParseRequest) -> ParseResult:
        try:
            result = self.inner.parse(request)
        except BackendUnavailable:
            self.parses.append(SavedParse(reason=ClarifyReason.UNAVAILABLE.value))
            raise
        except Exception:
            self.parses.append(SavedParse(reason=ClarifyReason.UNCLEAR.value))
            raise
        self.parses.append(_save_parse(result))
        return result


@dataclass
class _Replay:
    """Stands in for both backends while a save is replayed, so no model is called."""

    parses: list[SavedParse] = field(default_factory=list)
    line: str = ""
    broken: bool = False  # `Game` fails closed on a parser's error, so that alone would hide it

    def parse(self, request: ParseRequest) -> ParseResult:
        try:
            return _load_parse(self.parses.pop(0))
        except (IndexError, ValueError):
            self.broken = True
            raise

    def write(self, request: LineRequest) -> LineResult:
        return LineResult(self.line)


@dataclass(frozen=True)
class TurnCard:
    number: int
    addressee: str
    speaker: str
    question: str
    line: str
    status: str
    cost: int
    conflicts: tuple["Conflict", ...]
    denial: bool


@dataclass(frozen=True)
class Note:
    id: str
    text: str


@dataclass(frozen=True)
class Conflict:
    first: str
    second: str
    text: str
    said: tuple[str, str]  # what the two ids stand for, so that nobody has to go and look them up


@dataclass(frozen=True)
class Notes:
    grid: Grid
    extras: tuple[str, ...]
    statements: tuple[Note, ...]
    conflicts: tuple[Conflict, ...]


@dataclass(frozen=True)
class Ending:
    """Spoilers: exists only after the accusation."""

    outcome: str
    mark: str
    accused: str
    lines: tuple[str, ...]
    truth: TruthParts
    share: str


@dataclass(frozen=True)
class State:
    version: str
    seed: int
    lang: str
    mode: str  # "rules", or "model" with the player's own key
    hints: bool  # false is hard mode, which shows no contradiction until the ending
    current: str
    used: int
    budget: int
    left: int
    spent_cny: float  # upper bound of what the player's key has paid in this game
    example: str
    sheet: Sheet
    turns: tuple[TurnCard, ...]
    notes: Notes
    ending: Ending | None


@dataclass(frozen=True)
class Check:
    """What the page shows before the one accusation is spent."""

    suspect: str
    name: str
    first: str
    second: str
    conflicts: bool  # always true in hard mode, where a warning would be a hint
    related: tuple[str, ...]


class SessionError(ValueError):
    """Something the player can fix. `text` is in their language."""

    def __init__(self, code: str, text: str) -> None:
        super().__init__(code)
        self.code, self.text = code, text


_ERRORS: dict[str, tuple[str, str]] = {
    "no_addressee": ("先选一个人再问。", "Choose someone to ask first."),
    "too_long": (
        "问题太长了，一次问一个人、一个时段。",
        "That is too long. One person and one time per question.",
    ),
    "game_over": ("问题用完了，现在请指认。", "No questions left. Make your accusation."),
    "already_accused": ("已经指认过了。", "The accusation has been made."),
    "started": (
        "开始提问后不能再改困难模式。",
        "Hard mode cannot change once you have started asking.",
    ),
}


def _error(code: str, lang: Lang) -> SessionError:
    zh, en = _ERRORS[code]
    return SessionError(code, zh if lang is Lang.ZH else en)


class WebSession:
    def __init__(
        self, seed: int, lang: Lang, saved: SavedGame | None = None, hints: bool = True
    ) -> None:
        self.seed = seed
        self.mode = "rules"
        self.hints = saved.hints if saved is not None else hints
        self.current = ""
        self.prompt_tokens = self.completion_tokens = 0
        self._parser = _Recording(RuleParser())
        self._writer: LineWriter = TemplateWriter()
        self._saved: list[SavedTurn] = []
        self._accusation: SavedAccusation | None = None
        self.game = Game(daily_case(seed).case, self._parser, self._writer, lang)
        if saved is not None:
            self._replay(saved)
        self.game.lang = lang

    def _replay(self, saved: SavedGame) -> None:
        replay = _Replay()
        self.game.parser, self.game.writer = replay, replay
        for turn in saved.turns:
            replay.parses, replay.line = list(turn.parses), turn.line
            self.game.lang = Lang(turn.lang)
            said = self.game.ask(PersonId(turn.addressee), turn.question).line
            if replay.broken or replay.parses or said != turn.line:
                raise ValueError("this save does not replay to what it recorded")
            self.current = turn.addressee
        self.game.parser, self.game.writer = self._parser, self._writer
        self._saved = list(saved.turns)
        self.prompt_tokens = saved.prompt_tokens
        self.completion_tokens = saved.completion_tokens
        if saved.accusation is not None:
            accused = saved.accusation
            self.game.accuse(PersonId(accused.suspect), accused.first, accused.second)
            self._accusation = accused

    # --- Backends --------------------------------------------------------------------------------

    def use_model(self, model: ChatModel) -> None:
        self._parser.inner = LLMParser(model)
        self._writer = self.game.writer = LLMWriter(model)
        self.mode = "model"

    def use_rules(self) -> None:
        self._parser.inner = RuleParser()
        self._writer = self.game.writer = TemplateWriter()
        self.mode = "rules"

    # --- Playing ---------------------------------------------------------------------------------

    def set_lang(self, lang: Lang) -> None:
        """Later lines come in `lang` and every view changes; what was said stays as it was said."""
        self.game.lang = lang

    def set_hints(self, on: bool) -> None:
        """Chosen before the first question: a card that says "hard" should mean the whole game."""
        if self.game.turns:
            raise _error("started", self.game.lang)
        self.hints = on

    def _showing_hints(self) -> bool:
        return self.hints or self.game.verdict is not None

    def ask(self, person: str, text: str) -> None:
        lang = self.game.lang
        addressee, question = addressee_of(self.game.lexicon, text.strip())
        if addressee is None:
            if person not in {p.id for p in self.game.case.view.world.people}:
                raise _error("no_addressee", lang)
            addressee = PersonId(person)
        self.current = addressee
        if not question.strip():
            return
        if len(question) > MAX_QUESTION:
            raise _error("too_long", lang)
        self._parser.parses = []
        try:
            turn = self.game.ask(addressee, question)
        except GameOver:
            raise _error("game_over", lang) from None
        usage = turn.parse_usage + turn.line_usage
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self._saved.append(
            SavedTurn(addressee, question, lang.value, tuple(self._parser.parses), turn.line)
        )

    def check(self, suspect: str, first: str, second: str) -> Check:
        game, lang = self.game, self.game.lang
        names = {p.id: p.name.get(lang) for p in game.case.view.world.people}
        try:
            a, b = game.check_accusation(PersonId(suspect), first, second)
        except GameOver:
            raise _error("already_accused", lang) from None
        except AccusationError as err:
            raise SessionError(err.key, problem_text(err, names, lang)) from None
        name = names[PersonId(suspect)]
        if not self.hints:
            return Check(suspect, name, a, b, True, ())
        related = tuple(
            conflict_text(x, y, lang) for x, y in game.notebook.conflicts() if {a, b} & {x, y}
        )
        return Check(suspect, name, a, b, game.notebook.in_conflict(a, b), related)

    def accuse(self, suspect: str, first: str, second: str) -> None:
        checked = self.check(suspect, first, second)
        self.game.accuse(PersonId(suspect), checked.first, checked.second)
        self._accusation = SavedAccusation(suspect, checked.first, checked.second)

    # --- Views -----------------------------------------------------------------------------------

    def _turn_card(self, turn: Turn, lang: Lang) -> TurnCard:
        world = self.game.case.view.world
        names = {p.id: p.name.get(lang) for p in world.people}
        return TurnCard(
            turn.number,
            turn.addressee,
            names[turn.addressee],
            turn.question,
            turn.line,
            status_of(turn, world, lang),
            turn.cost,
            tuple(self._conflict(a, b, lang) for a, b in turn.new_conflicts)
            if self._showing_hints()
            else (),
            turn.stance is Stance.DENY,
        )

    def _item_text(self, note_id: str, lang: Lang) -> str:
        item = self.game.notebook.lookup(note_id)
        if isinstance(item, Evidence):
            return f"{note_id} {item.text.get(lang)}"
        assert item is not None  # the notebook gave this id
        return f"{note_id} {describe(item, self.game.case.view.world, lang)}"

    def _conflict(self, a: str, b: str, lang: Lang) -> Conflict:
        return Conflict(
            a, b, conflict_text(a, b, lang), (self._item_text(a, lang), self._item_text(b, lang))
        )

    def _notes(self, lang: Lang) -> Notes:
        book = self.game.notebook
        grid, extras = notebook_grid(book.obtained_view(), lang)
        world = self.game.case.view.world
        return Notes(
            grid,
            extras,
            tuple(Note(i, describe(s, world, lang)) for i, s in book.statements),
            tuple(self._conflict(a, b, lang) for a, b in book.conflicts())
            if self._showing_hints()
            else (),
        )

    def _ending(self, lang: Lang) -> Ending | None:
        game, verdict = self.game, self.game.verdict
        if verdict is None:
            return None
        names = {p.id: p.name.get(lang) for p in game.case.view.world.people}
        return Ending(
            verdict.outcome.value,
            mark(verdict),
            names[verdict.accused],
            tuple(ending_lines(game, lang)),
            truth_parts(game.case, lang),
            share_card(self.seed, verdict, game.turns, lang, hard=not self.hints),
        )

    def _example(self, lang: Lang) -> str:
        view = self.game.case.view
        slot = view.world.slots[view.crime.window[0]].label.split("–")[0]
        return f"{slot} 你在哪？" if lang is Lang.ZH else f"Where were you at {slot}?"

    def state(self) -> State:
        game, lang = self.game, self.game.lang
        spent = Usage(prompt_tokens=self.prompt_tokens, completion_tokens=self.completion_tokens)
        return State(
            __version__,
            self.seed,
            lang.value,
            self.mode,
            self.hints,
            self.current,
            game.used,
            game.budget,
            game.left,
            load_backends()[BACKEND].cost(spent),
            self._example(lang),
            sheet_parts(game.case.view, lang),
            tuple(self._turn_card(t, lang) for t in game.turns),
            self._notes(lang),
            self._ending(lang),
        )

    def save(self) -> str:
        return to_json(
            SavedGame(
                SAVE_VERSION,
                self.seed,
                self.prompt_tokens,
                self.completion_tokens,
                tuple(self._saved),
                self._accusation,
                self.hints,
            )
        )


def to_json(value: Any) -> str:
    """A frozen dataclass as JSON for the page."""
    return json.dumps(asdict(value), ensure_ascii=False)


def open_session(
    seed: int, lang: Lang, saved_text: str, hints: bool = True
) -> tuple[WebSession, bool]:
    """The session for this case, and whether a save existed that could not be used. `hints` is for
    a new game; a saved game keeps what it was started with."""
    if not saved_text:
        return WebSession(seed, lang, hints=hints), False
    saved = read_save(saved_text, seed)
    if saved is None:
        return WebSession(seed, lang, hints=hints), True
    try:
        return WebSession(seed, lang, saved), False
    except (ValueError, IndexError, KeyError, GameOver, AccusationError):
        return WebSession(seed, lang, hints=hints), True
