"""Model backends with a fake model: prompts, strict reply reading, the time guard, fail closed."""

import json
from dataclasses import dataclass, field

import pytest

from loosethread.content import load_pack
from loosethread.game import Game
from loosethread.generator import DAILY, generate
from loosethread.lexicon import Lexicon
from loosethread.lines import TemplateWriter, line_payload
from loosethread.llm.client import Completion, MissingKey, OpenAIChat
from loosethread.llm.config import Backend, load_backends
from loosethread.llm.parser import LLMParser, parse_prompt, read_reply, time_guard
from loosethread.llm.writer import LLMWriter, line_prompt
from loosethread.lookup import AnswerBook
from loosethread.model import Lang, LocationId, PersonId, Query, QueryKind, SlotIndex
from loosethread.npc import ClarifyReason, LineRequest, ParseRequest, Usage
from loosethread.parser import RuleParser

CASE = generate(213, DAILY).case
VIEW = CASE.view
LEX = Lexicon.build(VIEW.world, VIEW.crime, load_pack())
LIN, CHEN = PersonId("lin"), PersonId("chen")
KITCHEN = LocationId("kitchen")
USED = Usage(calls=1, prompt_tokens=900, completion_tokens=20, seconds=0.5)


@dataclass
class _Fake:
    """Replies with fixed texts in turn and keeps every prompt it was sent."""

    replies: list[str]
    finish: str = "stop"
    prompts: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, user: str, *, json_mode: bool, max_tokens: int) -> Completion:
        self.prompts.append((system, user))
        return Completion(self.replies.pop(0), USED, self.finish)


def _request(question: str, to: PersonId = LIN) -> ParseRequest:
    return ParseRequest(question, to, LEX)


# --- Parser --------------------------------------------------------------------------------------


def test_parse_prompt_holds_names_slots_and_the_question_only() -> None:
    system, user = parse_prompt(_request("你 21:15 在哪？"))
    data = json.loads(user)
    assert set(data) == {"addressee", "people", "locations", "items", "slots", "question"}
    assert data["question"] == "你 21:15 在哪？"
    assert data["addressee"]["id"] == "lin"
    assert data["slots"][5] == {"slot": 5, "from": "21:15", "to": "21:30"}
    assert {p["id"] for p in data["people"]} == {p.id for p in VIEW.world.people}
    for marker in ("culprit", "thief", "犯人", "真相"):
        assert marker not in user
    assert "Never answer the question" in system


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('{"kind": "where", "slot": 5}', Query(QueryKind.WHERE, LIN, slot=SlotIndex(5))),
        (  # fields the kind does not use are dropped
            '{"kind": "where", "slot": 2, "location": "kitchen", "person": null}',
            Query(QueryKind.WHERE, LIN, slot=SlotIndex(2)),
        ),
        ('{"kind": "when", "location": "kitchen"}', Query(QueryKind.WHEN, LIN, location=KITCHEN)),
        ('{"kind": "saw_person", "person": "chen"}', Query(QueryKind.SAW_PERSON, LIN, person=CHEN)),
        ('{"clarify": "one_slot"}', ClarifyReason.ONE_SLOT),
    ],
)
def test_read_reply_accepts_valid_replies(reply: str, expected: Query | ClarifyReason) -> None:
    assert read_reply(reply, _request("?")) == expected


@pytest.mark.parametrize(
    ("reply", "defect"),
    [
        ("Lin was in the lobby.", "not_json"),
        ("[1, 2]", "not_object"),
        ('{"clarify": "maybe"}', "bad_reason"),
        ('{"kind": "who_did_it"}', "bad_kind"),
        ('{"kind": "where", "slot": 99}', "bad_slot"),
        ('{"kind": "where", "slot": true}', "bad_slot"),
        ('{"kind": "when", "location": "moon"}', "unknown_id"),
        ('{"kind": "when", "location": "chen"}', "unknown_id"),  # a person is not a place
        ('{"kind": "where"}', "bad_shape"),
        ('{"kind": "saw_person", "person": "lin"}', "bad_shape"),  # herself
    ],
)
def test_read_reply_rejects_everything_else(reply: str, defect: str) -> None:
    with pytest.raises(ValueError, match=defect):
        read_reply(reply, _request("?"))


@pytest.mark.parametrize(
    ("question", "query", "expected"),
    [
        ("你 21:15 在哪？", Query(QueryKind.WHERE, LIN, slot=SlotIndex(5)), None),
        (
            "你 21:15 在哪？",
            Query(QueryKind.WHERE, LIN, slot=SlotIndex(4)),
            ClarifyReason.NEED_TIME,
        ),
        ("20:22 之后你去了哪？", Query(QueryKind.WHERE, LIN, slot=SlotIndex(2)), "need_time"),
        ("20:15–21:00 你在哪？", Query(QueryKind.WHERE, LIN, slot=SlotIndex(1)), "one_slot"),
        ("案发时你在哪？", Query(QueryKind.WHERE, LIN, slot=SlotIndex(2)), "need_time"),
        ("8:30 你见过陈墨吗", Query(QueryKind.SAW_PERSON, LIN, person=CHEN), "need_time"),
        ("你见过陈墨吗", Query(QueryKind.SAW_PERSON, LIN, person=CHEN), None),
        ("20:15–21:00 你去过厨房吗", Query(QueryKind.WHEN, LIN, location=KITCHEN), None),
    ],
)
def test_time_guard(question: str, query: Query, expected: str | None) -> None:
    reason = time_guard(query, _request(question))
    assert (reason.value if reason else None) == (
        expected.value if isinstance(expected, ClarifyReason) else expected
    )


def test_parser_returns_queries_and_counts_usage() -> None:
    fake = _Fake(['{"kind": "where", "slot": 5}', '{"kind": "where", "slot": 2}'])
    parser = LLMParser(fake)
    good = parser.parse(_request("九点一刻你在干嘛"))
    assert (good.query, good.usage) == (Query(QueryKind.WHERE, LIN, slot=SlotIndex(5)), USED)
    guarded = parser.parse(_request("20:22 之后你去了哪？"))
    assert (guarded.query, guarded.reason) == (None, ClarifyReason.NEED_TIME)
    assert len(fake.prompts) == 2


def test_bad_replies_cost_nothing_in_the_game_but_their_usage_is_kept() -> None:
    fake = _Fake(["not json", '{"kind": "when", "location": "moon"}'])
    game = Game(CASE, LLMParser(fake), TemplateWriter(), Lang.ZH)
    first = game.ask(LIN, "你 21:15 在哪？")
    second = game.ask(LIN, "你什么时候去过月亮？")
    assert (first.cost, first.problems, first.parse_usage) == (
        0,
        ("parser_invalid:not_json",),
        USED,
    )
    assert (second.cost, second.problems) == (0, ("parser_invalid:unknown_id",))
    assert game.used == 0


# --- Writer --------------------------------------------------------------------------------------


def test_writer_prompt_is_the_line_payload_and_lines_are_post_checked() -> None:
    scene = next(x.name.zh for x in VIEW.world.locations if x.id == VIEW.crime.location)
    fake = _Fake(["我那会儿在大堂，一个人。", f"我在{scene}。"])
    game = Game(CASE, RuleParser(), LLMWriter(fake), Lang.ZH)
    kept = game.ask(LIN, "你 21:15 在哪？")  # she answers 大堂 for this slot
    assert (kept.problems, kept.line) == ((), "我那会儿在大堂，一个人。")
    replaced = game.ask(LIN, "你 20:00 在哪？")
    assert replaced.problems == (f"line_unauthorised:{scene}",)
    assert scene not in replaced.line
    system, user = fake.prompts[0]
    assert "Simplified Chinese" in system
    assert json.loads(user)["stance"] == "answer"


def test_writer_payload_matches_the_template_request() -> None:
    fake = _Fake(["好。"])
    game = Game(CASE, RuleParser(), LLMWriter(fake), Lang.EN)
    game.ask(LIN, "Where were you at 9:15?")
    payload = json.loads(fake.prompts[0][1])
    assert payload["lang"] == "en"
    assert payload["question"] == {"kind": "where", "time": "21:15 and 21:30"}


def test_the_writer_sends_exactly_the_line_payload() -> None:
    lin = next(p for p in VIEW.world.people if p.id == LIN)
    query = Query(QueryKind.WHERE, LIN, slot=SlotIndex(5))
    facts = AnswerBook.from_truth(VIEW.world, CASE.truth).answer(query)
    request = LineRequest(Lang.EN, lin, facts, VIEW.world)
    system, user = line_prompt(request)
    assert user == line_payload(request)
    assert "English" in system


def test_a_cut_off_line_falls_back_to_the_template() -> None:
    fake = _Fake(["我在"], finish="length")
    game = Game(CASE, RuleParser(), LLMWriter(fake), Lang.ZH)
    turn = game.ask(LIN, "这雨下得真大")
    assert turn.problems == ("writer_invalid:too_long",)
    assert turn.line == "是啊，这雨下得人心里发慌。"
    assert turn.line_usage == USED


# --- Config and client ---------------------------------------------------------------------------


def test_config_names_models_and_prices() -> None:
    backends = load_backends()
    assert {"deepseek", "local"} <= set(backends)
    deepseek = backends["deepseek"]
    assert deepseek.api_key_env == "DEEPSEEK_API_KEY"
    assert deepseek.cost(Usage(1, 1_000_000, 1_000_000, 1.0)) == pytest.approx(
        deepseek.price_input + deepseek.price_output
    )
    assert backends["local"].cost(USED) == 0.0


def _backend(**changes: object) -> Backend:
    base = load_backends()["local"]
    return Backend(**{**base.__dict__, **changes})


def test_a_missing_key_is_reported_by_variable_name_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOOSETHREAD_TEST_KEY", raising=False)
    with pytest.raises(MissingKey, match="LOOSETHREAD_TEST_KEY is not set"):
        OpenAIChat(_backend(api_key_env="LOOSETHREAD_TEST_KEY"))


def test_an_unserved_model_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    model = OpenAIChat(_backend())  # constructing the client makes no request
    monkeypatch.setattr(model, "models", lambda: ("some-other-model",))
    with pytest.raises(RuntimeError, match="is not served"):
        model.check_model()
    monkeypatch.setattr(model, "models", lambda: (model.backend.model,))
    model.check_model()
