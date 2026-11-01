"""Game session: budget, notebook, accusation outcomes, fail-closed backends, prompt isolation."""

import json
from dataclasses import dataclass, field, replace

import pytest

from loosethread.content import load_pack
from loosethread.difficulty import question_plan
from loosethread.game import AccusationError, Game, GameOver, Outcome, Turn
from loosethread.generator import DAILY, PACKS, SHAPE_PARAMS, AlibiStyle, generate
from loosethread.lines import TemplateWriter, line_payload, template_line
from loosethread.lookup import AnswerBook, in_scope_queries
from loosethread.model import (
    Case,
    Lang,
    LocationId,
    Occupants,
    PersonAt,
    PersonId,
    Query,
    QueryKind,
    Stance,
    Tone,
)
from loosethread.npc import (
    IRRITATED_AFTER,
    BackendUnavailable,
    ClarifyReason,
    LineRequest,
    LineResult,
    ParseRequest,
    ParseResult,
    Usage,
)
from loosethread.parser import RuleParser, canonical_question
from loosethread.solver import Solver

CASE = generate(213, DAILY).case
VIEW = CASE.view
CULPRIT = CASE.truth.culprit
INNOCENT = next(p for p in sorted(VIEW.suspects) if p != CULPRIT)
CLIENT = next(p.id for p in VIEW.world.people if p.id not in VIEW.suspects)


def _game(case: Case = CASE, budget: int = 20, **backends: object) -> Game:
    parser = backends.get("parser", RuleParser())
    writer = backends.get("writer", TemplateWriter())
    return Game(case, parser, writer, Lang.ZH, budget=budget)  # type: ignore[arg-type]


def _ask(game: Game, query: Query) -> Turn:
    return game.ask(query.addressee, canonical_question(query, game.case.view.world, game.lang))


def _exposing_pairs(game: Game) -> list[tuple[str, str]]:
    return [p for p in game.notebook.conflicts() if game.exposes_culprit_lie(*p)]


# --- Solving -------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 3, 213])
def test_plan_then_culprit_questions_solve_the_case(seed: int) -> None:
    case = generate(seed, DAILY).case
    game = _game(case, budget=60)
    plan = question_plan(case.view, Solver(case.view))[0]
    for query in plan:
        asked = _ask(game, query).query
        assert asked == (
            replace(query, kind=QueryKind.WITH_WHOM) if query.kind is QueryKind.WHERE else query
        )
    from_plan = bool(_exposing_pairs(game))
    # The oracle plan may rule suspects out by elimination alone. Then the lie has to be found:
    # the culprit's story for the window, and who else was in the rooms they name.
    window = case.view.crime.window
    culprit = case.truth.culprit
    extra = [Query(QueryKind.WHERE, culprit, slot=t) for t in window]
    extra += [
        Query(QueryKind.WITH_WHOM, p.id, slot=t)
        for t in window
        for p in case.view.world.people
        if p.id != culprit
    ]
    for query in extra:
        if _exposing_pairs(game):
            break
        _ask(game, query)
    pair = _exposing_pairs(game)[0]
    verdict = game.accuse(case.truth.culprit, *pair)
    assert verdict.outcome is Outcome.SOLVED
    assert verdict.min_questions == len(plan)
    if from_plan:
        assert verdict.stars == 3


def test_wrong_suspect_and_hunch() -> None:
    game = _game()
    assert game.accuse(INNOCENT, "E1", "E2").outcome is Outcome.WRONG
    with pytest.raises(GameOver):
        game.accuse(CULPRIT, "E1", "E2")
    game = _game()
    with pytest.raises(RuntimeError, match="only after the accusation"):
        game.exposing_pairs()
    hunch = game.accuse(CULPRIT, "E1", "E2")
    assert (hunch.outcome, hunch.stars, hunch.exposes_lie) == (Outcome.HUNCH, 0, False)
    assert game.exposing_pairs() == ()


@pytest.mark.parametrize(
    ("suspect", "first", "second", "key"),
    [
        (CLIENT, "E1", "E2", "not_suspect"),
        (CULPRIT, "S9", "E1", "unknown_item"),
        (CULPRIT, "E1", "e1", "same_item"),
    ],
)
def test_malformed_accusations_are_rejected_without_ending_the_game(
    suspect: PersonId, first: str, second: str, key: str
) -> None:
    game = _game()
    with pytest.raises(AccusationError) as err:
        game.accuse(suspect, first, second)
    assert err.value.key == key
    assert game.verdict is None


# --- Budget and turns ----------------------------------------------------------------------------


def test_clarifications_and_repeats_are_free() -> None:
    game = _game()
    unclear = game.ask(CULPRIT, "嗯……")
    assert (unclear.cost, unclear.query, unclear.stance) == (0, None, Stance.CLARIFY)
    query = Query(QueryKind.WHERE, INNOCENT, slot=VIEW.crime.window[0])
    first, again = _ask(game, query), _ask(game, query)
    assert (first.cost, again.cost, again.repeat) == (1, 0, True)
    assert again.line == "刚才说过了：" + first.line
    assert first.new_notes == ("S1",)
    assert again.new_notes == ()
    assert game.used == 1


def test_where_is_answered_with_the_company_so_asking_who_after_it_is_free() -> None:
    game = _game()
    slot = VIEW.crime.window[0]
    first = _ask(game, Query(QueryKind.WHERE, INNOCENT, slot=slot))
    assert first.query == Query(QueryKind.WITH_WHOM, INNOCENT, slot=slot)
    ((_, statement),) = game.notebook.statements
    assert isinstance(statement.claim, Occupants)
    again = _ask(game, Query(QueryKind.WITH_WHOM, INNOCENT, slot=slot))
    assert (first.cost, again.cost, again.repeat, game.used) == (1, 0, True, 1)


def test_the_culprit_lie_shows_on_a_where_question_alone() -> None:
    """D-028: asking the liar and a witness "where" must raise the hint."""
    for seed in (0, 3, 213):
        case = generate(seed, DAILY).case
        (lie, *_) = (x for x in case.truth.lies if x.statement.speaker == case.truth.culprit)
        claim = lie.statement.claim
        assert isinstance(claim, PersonAt)
        game = _game(case, budget=60)
        _ask(game, Query(QueryKind.WHERE, case.truth.culprit, slot=claim.slot))
        witnesses = [
            f.person
            for f in case.truth.timeline
            if f.slot == claim.slot and f.location == claim.location
        ]
        assert any(
            _ask(game, Query(QueryKind.WHERE, w, slot=claim.slot)).new_conflicts for w in witnesses
        )
        assert _exposing_pairs(game)


def test_answers_without_case_facts_are_free() -> None:
    game = _game()
    other = next(p for p in sorted(VIEW.suspects) if p != INNOCENT)
    for query in (
        Query(QueryKind.SMALL_TALK, INNOCENT),
        Query(QueryKind.OUT_OF_SCOPE, INNOCENT),
        Query(QueryKind.OPINION, INNOCENT, person=other),
    ):
        turn = _ask(game, query)
        assert (turn.query, turn.cost, turn.repeat, turn.new_notes) == (query, 0, False, ())
        assert turn.stance is Stance.DEFLECT
    assert game.used == 0


def test_a_denial_still_costs_a_question() -> None:
    game = _game()
    never = next(
        loc.id
        for loc in VIEW.world.locations
        if not game._book.answer(Query(QueryKind.WHEN, INNOCENT, location=loc.id)).claims
    )
    turn = _ask(game, Query(QueryKind.WHEN, INNOCENT, location=never))
    assert (turn.stance, turn.cost) == (Stance.DENY, 1)


def test_a_follow_up_takes_the_time_just_discussed() -> None:
    other = next(p for p in sorted(VIEW.suspects) if p != INNOCENT)
    parser = _Recorder()
    game = _game(parser=parser)
    assert game.ask(INNOCENT, "你和谁在一起？").reason is ClarifyReason.NEED_TIME  # nothing yet
    start = game.case.view.world.slots[VIEW.crime.window[0]].label.split("–")[0]
    first = game.ask(INNOCENT, f"{start} 你在哪？")
    same = game.ask(INNOCENT, "那你那会儿跟谁在一起？")
    assert same.query == first.query
    assert (same.cost, same.repeat) == (0, True)
    assert parser.parses[-1].question == f"{start} 那你那会儿跟谁在一起？"
    switched = game.ask(other, "你身边有谁？")  # the time carries over to the next person
    assert switched.query == Query(QueryKind.WITH_WHOM, other, slot=VIEW.crime.window[0])
    assert switched.cost == 1


@pytest.mark.parametrize(
    "question",
    [
        "后来你和谁在一起？",
        "今晚你和谁在一起？",
        "and who was with you after that?",
        "21:00 之后你在哪？",
    ],
)
def test_no_follow_up_for_relative_words_or_the_whole_evening(question: str) -> None:
    parser = _Recorder()
    game = _game(parser=parser)
    game.ask(INNOCENT, "20:15 你在哪？")
    asked = len(parser.parses)
    turn = game.ask(INNOCENT, question)
    assert (turn.reason, turn.cost) == (ClarifyReason.NEED_TIME, 0)
    assert len(parser.parses) == asked + 1  # no second reading


@dataclass
class _NeedsTime:
    """A parser that never reads a time, then answers `second` once a time is put in front."""

    second: ParseResult | Exception

    def parse(self, request: ParseRequest) -> ParseResult:
        if request.question.startswith("20:15 "):
            if isinstance(self.second, Exception):
                raise self.second
            return self.second
        if request.question == "20:15":
            slot = next(s.index for s in VIEW.world.slots if s.label.startswith("20:15"))
            return ParseResult(Query(QueryKind.WHERE, request.addressee, slot=slot), usage=_ONE)
        return ParseResult(None, ClarifyReason.NEED_TIME, _ONE)


_ONE = Usage(calls=1)


@pytest.mark.parametrize(
    ("second", "reason", "problems", "calls"),
    [
        (ParseResult(None, ClarifyReason.UNCLEAR, _ONE), ClarifyReason.NEED_TIME, (), 2),
        (BackendUnavailable("APITimeoutError"), ClarifyReason.UNAVAILABLE,
         ("parser_unavailable:APITimeoutError",), 1),
    ],
)  # fmt: skip
def test_a_second_reading_that_fails_stays_free(
    second: ParseResult | Exception,
    reason: ClarifyReason,
    problems: tuple[str, ...],
    calls: int,
) -> None:
    game = _game(parser=_NeedsTime(second))
    game.ask(INNOCENT, "20:15")
    turn = game.ask(INNOCENT, "那会儿呢？")
    assert (turn.reason, turn.cost, turn.problems) == (reason, 0, problems)
    assert turn.parse_usage.calls == calls


class _NoReading:
    """A parser that asks which time, whatever the question says."""

    def parse(self, request: ParseRequest) -> ParseResult:
        return ParseResult(None, ClarifyReason.NEED_TIME, _ONE)


def test_a_question_that_names_a_time_is_answered_for_that_time() -> None:
    """ "那九点呢" gives a model nothing but the time, and it asked which time."""
    game = _game(parser=_NoReading())
    slot = next(s.index for s in VIEW.world.slots if s.label.startswith("21:00"))
    turn = game.ask(INNOCENT, "那九点呢")
    assert turn.query == Query(QueryKind.WITH_WHOM, INNOCENT, slot=slot)
    assert turn.cost == 1
    relative = game.ask(INNOCENT, "九点以后呢")  # an anchor: still which time
    assert (relative.reason, relative.cost) == (ClarifyReason.NEED_TIME, 0)


class _Unclear:
    """A parser that follows nothing, as a model may on a bare time."""

    def parse(self, request: ParseRequest) -> ParseResult:
        return ParseResult(None, ClarifyReason.UNCLEAR, _ONE)


def test_an_unclear_reading_of_nothing_but_a_time_is_answered_for_that_time() -> None:
    game = _game(parser=_Unclear())
    slot = next(s.index for s in VIEW.world.slots if s.label.startswith("21:15"))
    turn = game.ask(INNOCENT, "and after that, around 9:20?")
    assert turn.query == Query(QueryKind.WITH_WHOM, INNOCENT, slot=slot)
    other = game.ask(INNOCENT, "did you argue at 9:20?")  # it says something else: still free
    assert (other.reason, other.cost) == (ClarifyReason.UNCLEAR, 0)


def test_where_were_you_when_it_went_missing_asks_which_time() -> None:
    game = _game()
    start = VIEW.world.slots[VIEW.crime.window[0]].label.split("–")[0]
    game.ask(INNOCENT, f"{start} 你在哪？")
    turn = game.ask(INNOCENT, "东西被偷的时候你在哪？")
    assert (turn.reason, turn.cost) == (ClarifyReason.NEED_TIME, 0)  # not the last time discussed


@pytest.mark.parametrize("style", list(AlibiStyle))
def test_every_lie_shape_raises_the_hint_and_can_be_solved_in_play(style: AlibiStyle) -> None:
    for pack_id in PACKS:
        case = generate(7, SHAPE_PARAMS[style], load_pack(pack_id)).case
        game = _game(case, budget=120)
        view = case.view
        for person in view.world.people:
            for slot in view.world.slots:
                if _exposing_pairs(game):
                    break
                _ask(game, Query(QueryKind.WHERE, person.id, slot=slot.index))
        pair = _exposing_pairs(game)[0]
        assert game.notebook.in_conflict(*pair)
        assert game.accuse(case.truth.culprit, *pair).outcome is Outcome.SOLVED


def test_a_named_companion_is_said_to_be_there_and_says_otherwise() -> None:
    case = generate(7, SHAPE_PARAMS[AlibiStyle.COMPANION]).case
    culprit = case.truth.culprit
    claim = next(x.statement.claim for x in case.truth.lies if x.statement.speaker == culprit)
    assert isinstance(claim, Occupants)
    (companion,) = claim.people - {culprit}
    game = _game(case)
    first = _ask(game, Query(QueryKind.WHERE, culprit, slot=claim.slot))
    names = {p.id: p.name.zh for p in case.view.world.people}
    assert names[companion] in first.line
    second = _ask(game, Query(QueryKind.WHERE, companion, slot=claim.slot))
    assert second.new_conflicts
    book = AnswerBook.from_truth(case.view.world, case.truth)
    saw = book.answer(Query(QueryKind.SAW_PERSON, culprit, person=companion))
    assert any(
        isinstance(s.claim, PersonAt) and s.claim.slot == claim.slot and s.claim.person == companion
        for s in saw.claims
    )


def test_budget_runs_out() -> None:
    game = _game(budget=1)
    _ask(game, Query(QueryKind.WHERE, INNOCENT, slot=VIEW.crime.window[0]))
    assert game.left == 0
    with pytest.raises(GameOver):
        game.ask(INNOCENT, "你 20:00 在哪？")


def test_tone_turns_irritated_after_many_questions() -> None:
    game = _game()
    turns = [
        _ask(game, Query(QueryKind.WHERE, INNOCENT, slot=s.index))
        for s in VIEW.world.slots[: IRRITATED_AFTER + 1]
    ]
    assert [t.tone for t in turns[:IRRITATED_AFTER]] == [Tone.CALM] * IRRITATED_AFTER
    assert turns[-1].tone is Tone.IRRITATED
    assert turns[-1].line.startswith("你问得可真多。")


# --- Fail closed ---------------------------------------------------------------------------------


class _Broken:
    def parse(self, request: ParseRequest) -> ParseResult:
        raise RuntimeError("backend down")

    def write(self, request: LineRequest) -> LineResult:
        raise RuntimeError("backend down")


@dataclass
class _Fixed:
    """A parser that always returns one query, and a writer that always says one line."""

    query: Query | None = None
    line: str = ""

    def parse(self, request: ParseRequest) -> ParseResult:
        assert self.query is not None
        return ParseResult(self.query)

    def write(self, request: LineRequest) -> LineResult:
        return LineResult(self.line)


def test_parser_failures_mean_rephrase_at_no_cost() -> None:
    game = _game(parser=_Broken())
    turn = game.ask(INNOCENT, "你 20:00 在哪？")
    assert (turn.cost, turn.query, turn.problems) == (0, None, ("parser_error:RuntimeError",))
    other = Query(QueryKind.WHERE, CULPRIT, slot=VIEW.crime.window[0])
    turn = _game(parser=_Fixed(query=other)).ask(INNOCENT, "?")
    assert (turn.cost, turn.problems) == (0, ("parser_wrong_addressee",))
    moon = Query(QueryKind.WHEN, INNOCENT, location=LocationId("moon"))
    turn = _game(parser=_Fixed(query=moon)).ask(INNOCENT, "?")
    assert (turn.cost, turn.problems) == (0, ("parser_unknown_name",))


def test_bad_lines_fall_back_to_the_template() -> None:
    query = Query(QueryKind.SMALL_TALK, INNOCENT)
    scene = next(x.name.zh for x in VIEW.world.locations if x.id == VIEW.crime.location)
    for writer, problem in (
        (_Broken(), "writer_error:RuntimeError"),
        (_Fixed(line=""), "line_empty"),
        (_Fixed(line=f"我刚才在{scene}。"), f"line_unauthorised:{scene}"),
    ):
        game = _game(writer=writer)
        turn = _ask(game, query)
        assert turn.problems == (problem,)
        assert turn.line == "是啊，今晚谁心里都不踏实。"


# --- Prompt isolation ----------------------------------------------------------------------------


@dataclass
class _Recorder:
    """Passes through to the offline backends and keeps every request a model would receive."""

    parses: list[ParseRequest] = field(default_factory=list)
    lines: list[LineRequest] = field(default_factory=list)

    def parse(self, request: ParseRequest) -> ParseResult:
        self.parses.append(request)
        return RuleParser().parse(request)

    def write(self, request: LineRequest) -> LineResult:
        self.lines.append(request)
        return TemplateWriter().write(request)


@pytest.mark.parametrize("seed", [0, 7, 213])
def test_every_backend_request_stays_inside_the_answer_table(seed: int) -> None:
    case = generate(seed, DAILY).case
    world, truth = case.view.world, case.truth
    recorder = _Recorder()
    queries = in_scope_queries(world)
    game = _game(case, budget=len(queries), parser=recorder, writer=recorder)
    for asked in queries:
        _ask(game, asked)
    book = AnswerBook.from_truth(world, truth)
    (theft,) = truth.events
    assert len(recorder.lines) == len(queries)
    for request in recorder.lines:
        query = request.facts.query
        assert query is not None
        # The writer got exactly what the answer table allows for this query, nothing more.
        assert replace(request.facts, tone=None) == book.answer(query)
        for claim in (c.claim for c in request.facts.claims):
            match claim:
                case PersonAt(person, location, slot):
                    assert (person, location, slot) != (truth.culprit, theft.location, theft.slot)
                case Occupants(location, slot, people):
                    assert not (
                        location == theft.location
                        and slot == theft.slot
                        and truth.culprit in people
                    )
        payload = line_payload(request)
        json.loads(payload)
        for marker in ("culprit", "thief", "truth", "犯人", "谎", "真相"):
            assert marker not in payload
        assert template_line(request) in [t.line for t in game.turns]
    assert [r.question for r in recorder.parses] == [t.question for t in game.turns]
