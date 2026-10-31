"""Model backends with a fake model: prompts, strict reply reading, the time guard, fail closed."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from loosethread.content import load_pack
from loosethread.game import Game
from loosethread.generator import DAILY, generate
from loosethread.lexicon import Lexicon
from loosethread.lines import TemplateWriter, line_payload
from loosethread.llm.client import Completion, MissingKey, OpenAIChat
from loosethread.llm.config import Backend, load_backends
from loosethread.llm.parser import (
    LLMParser,
    examples,
    one_slot_ranges,
    parse_prompt,
    read_reply,
    time_guard,
)
from loosethread.llm.writer import LLMWriter, line_prompt
from loosethread.lookup import AnswerBook
from loosethread.model import Lang, LocationId, PersonId, Query, QueryKind, SlotIndex
from loosethread.npc import ClarifyReason, LineRequest, ParseRequest, Usage
from loosethread.parser import RuleParser
from loosethread.parser_eval import SET, load_items

CASE = generate(213, DAILY).case
VIEW = CASE.view
LEX = Lexicon.build(VIEW.world, VIEW.crime, load_pack())
LIN, CHEN = PersonId("lin"), PersonId("chen")
KITCHEN = LocationId("kitchen")
ROOT = Path(__file__).resolve().parents[1]
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


def test_parse_prompt_holds_names_examples_and_the_question_only() -> None:
    system, user = parse_prompt(_request("你 21:15 在哪？"))
    data = json.loads(user)
    assert set(data) == {
        "addressee", "people", "locations", "items", "evening", "examples", "question"
    }  # fmt: skip
    assert data["question"] == "你 21:15 在哪？"
    assert data["addressee"]["id"] == "lin"
    assert data["evening"] == {"from": "20:00", "to": "22:00"}
    assert {p["id"] for p in data["people"]} == {p.id for p in VIEW.world.people}
    for marker in ("culprit", "thief", "犯人", "真相"):
        assert marker not in user
    assert "Never answer the question" in system


def test_worked_examples_parse_and_are_not_set_questions() -> None:
    asked = {item.question for item in load_items(ROOT / SET)}
    for seed in (213, 7, 42, 0):
        view = generate(seed, DAILY).case.view
        lex = Lexicon.build(view.world, view.crime, load_pack())
        for person in view.world.people:
            request = ParseRequest("?", person.id, lex)
            for example in examples(request):
                assert example["q"] not in asked
                read_reply(json.dumps(example["a"]), request)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('{"kind": "where", "time": "21:15"}', Query(QueryKind.WHERE, LIN, slot=SlotIndex(5))),
        ('{"kind": "where", "time": "21:29"}', Query(QueryKind.WHERE, LIN, slot=SlotIndex(5))),
        (  # fields the kind does not use are dropped
            '{"kind": "where", "time": "20:30", "location": "kitchen", "person": "lin"}',
            Query(QueryKind.WHERE, LIN, slot=SlotIndex(2)),
        ),
        ('{"kind": "where", "time": "23:00"}', ClarifyReason.BAD_TIME),
        (
            '{"kind": "where", "time": "20:15-20:30"}',
            Query(QueryKind.WHERE, LIN, slot=SlotIndex(1)),
        ),
        ('{"kind": "where", "time": "20:15-21:00"}', ClarifyReason.ONE_SLOT),
        ('{"kind": "with_whom", "time": null}', ClarifyReason.NEED_TIME),
        ('{"kind": "where", "slot": 5}', ClarifyReason.NEED_TIME),  # slots are not taken as given
        ('{"kind": "when", "location": "kitchen"}', Query(QueryKind.WHEN, LIN, location=KITCHEN)),
        (
            '{"kind": "saw_person", "person": "chen", "time": null}',
            Query(QueryKind.SAW_PERSON, LIN, person=CHEN),
        ),
        ('{"clarify": "one_slot"}', ClarifyReason.ONE_SLOT),
        ('{"clarify": "out_of_scope"}', Query(QueryKind.OUT_OF_SCOPE, LIN)),
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
        ('{"kind": "where", "time": "9pm"}', "bad_time_format"),
        ('{"kind": "where", "time": 21}', "bad_time_format"),
        ('{"kind": "where", "time": "21:75"}', "bad_time_format"),
        ('{"kind": "where", "time": "T"}', "bad_time_format"),
        ('{"kind": "when", "location": "moon"}', "unknown_id"),
        ('{"kind": "when", "location": "chen"}', "unknown_id"),  # a person is not a place
        ('{"kind": "opinion"}', "bad_shape"),
        ('{"kind": "saw_person", "person": "lin"}', "bad_shape"),  # herself
    ],
)
def test_read_reply_rejects_everything_else(reply: str, defect: str) -> None:
    with pytest.raises(ValueError, match=defect):
        read_reply(reply, _request("?"))


@pytest.mark.parametrize(
    ("question", "sent"),
    [
        ("20:15-20:30 你在哪里?和谁在一起?", "20:15 你在哪里?和谁在一起?"),
        ("８:１５～８:３０ 你在哪", "８:１５ 你在哪"),
        ("where were you 9:15 – 9:30?", "where were you 9:15?"),
        ("20:15 到 21:00 你都在哪", "20:15 到 21:00 你都在哪"),  # three slots: left for the model
        ("23:45-24:00 你在哪", "23:45-24:00 你在哪"),  # outside the evening
        ("20:22 之后你去了哪？", "20:22 之后你去了哪？"),
    ],
)
def test_a_range_of_exactly_one_slot_reaches_the_model_as_its_start(
    question: str, sent: str
) -> None:
    assert json.loads(parse_prompt(_request(question))[1])["question"] == sent


def test_no_question_in_the_frozen_set_is_rewritten() -> None:
    # The DeepSeek test measurement (D-025) predates the rewrite; it sent these same texts.
    for item in load_items(ROOT / SET):
        assert one_slot_ranges(item.question, LEX) == item.question, item.id


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("20:15 你在哪里?和谁在一起?", QueryKind.WITH_WHOM),
        ("Where were you at 8:15, and who was with you?", QueryKind.WITH_WHOM),
        ("20:15 你在哪里?", QueryKind.WHERE),
        ("沈怀山 20:15 在哪？", QueryKind.WHERE),  # a name is not a company word
    ],
)
def test_where_that_also_asks_for_company_reads_as_with_whom(
    question: str, kind: QueryKind
) -> None:
    got = read_reply('{"kind": "where", "time": "20:15"}', _request(question))
    assert got == Query(kind, LIN, slot=SlotIndex(1))


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
    fake = _Fake(['{"kind": "where", "time": "21:15"}', '{"kind": "where", "time": "20:30"}'])
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


def test_a_cut_off_parse_is_refused_even_if_it_reads() -> None:
    fake = _Fake(['{"kind": "where", "time": "21:15"}'], finish="length")
    game = Game(CASE, LLMParser(fake), TemplateWriter(), Lang.ZH)
    turn = game.ask(LIN, "你 21:15 在哪？")
    assert (turn.cost, turn.problems, turn.parse_usage) == (0, ("parser_invalid:too_long",), USED)


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


@pytest.mark.parametrize(
    ("thinking", "reasoning", "extra", "budget"),
    [("", 0, None, 120), ("disabled", 0, {"thinking": {"type": "disabled"}}, 120),
     ("enabled", 1024, {"thinking": {"type": "enabled"}}, 1144)],
)  # fmt: skip
def test_thinking_mode_is_sent_and_reasoning_gets_its_own_budget(
    monkeypatch: pytest.MonkeyPatch,
    thinking: str,
    reasoning: int,
    extra: dict[str, object] | None,
    budget: int,
) -> None:
    model = OpenAIChat(_backend(thinking=thinking, reasoning_tokens=reasoning))
    sent: dict[str, object] = {}

    def create(**kwargs: object) -> object:
        sent.update(kwargs)
        raise ConnectionError  # stop before any reply is read

    monkeypatch.setattr(model._client.chat.completions, "create", create)
    with pytest.raises(ConnectionError):
        model.complete("s", "u", json_mode=True, max_tokens=120)
    assert (sent["extra_body"], sent["max_tokens"]) == (extra, budget)


def test_config_rejects_an_unknown_thinking_mode(tmp_path: Path) -> None:
    bad = tmp_path / "backends.toml"
    bad.write_text(
        '[x]\nbase_url = "u"\napi_key_env = ""\nmodel = "m"\nprice_input = 0\n'
        'price_output = 0\ntimeout = 1\nmax_retries = 0\nthinking = "maybe"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="bad thinking setting"):
        load_backends(bad)


def test_an_unserved_model_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    model = OpenAIChat(_backend())  # constructing the client makes no request
    monkeypatch.setattr(model, "models", lambda: ("some-other-model",))
    with pytest.raises(RuntimeError, match="is not served"):
        model.check_model()
    monkeypatch.setattr(model, "models", lambda: (model.backend.model,))
    model.check_model()
