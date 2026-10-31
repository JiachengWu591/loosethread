"""Game session: budget, notebook, accusation outcomes, fail-closed backends, prompt isolation."""

import json
from dataclasses import dataclass, field, replace

import pytest

from loosethread.difficulty import question_plan
from loosethread.game import AccusationError, Game, GameOver, Outcome, Turn
from loosethread.generator import DAILY, generate
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
from loosethread.npc import IRRITATED_AFTER, LineRequest, LineResult, ParseRequest, ParseResult
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
    return [p for p in game.notebook.conflicts() if game._exposes_culprit_lie(*p)]


# --- Solving -------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [0, 3, 213])
def test_plan_then_culprit_questions_solve_the_case(seed: int) -> None:
    case = generate(seed, DAILY).case
    game = _game(case, budget=60)
    plan = question_plan(case.view, Solver(case.view))[0]
    for query in plan:
        assert _ask(game, query).query == query
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
    hunch = _game().accuse(CULPRIT, "E1", "E2")
    assert (hunch.outcome, hunch.stars, hunch.exposes_lie) == (Outcome.HUNCH, 0, False)


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
        assert turn.line == "是啊，这雨下得人心里发慌。"


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
