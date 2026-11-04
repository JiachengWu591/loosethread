"""The browser version's Python side: session, save, share card, key handling and build."""

import ast
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

import pytest

import loosethread
from loosethread.case import truth_parts
from loosethread.generator import daily_case
from loosethread.llm.config import load_backends
from loosethread.model import Lang
from loosethread.npc import BackendUnavailable
from loosethread.web import bridge
from loosethread.web.browser_chat import BrowserChat, KeyRejected, ModelMissing
from loosethread.web.build import bundled_files, pack_package
from loosethread.web.session import (
    MAX_QUESTION,
    SavedGame,
    SessionError,
    WebSession,
    open_session,
    read_save,
    to_json,
)
from loosethread.web.share import (
    CONTRADICTION,
    LINK,
    NEW_FACT,
    NOTHING_NEW,
    mark,
    share_card,
    squares,
)

SEED = 20261104
SITE = Path(loosethread.__file__).parent / "web" / "site"
FAKE_KEY = "sk-this-is-a-fake-key-for-tests"


def _everyone(session: WebSession, limit: int = 100) -> None:
    """Ask every suspect about every slot of the theft window, up to `limit` questions."""
    view = session.game.case.view
    lang = session.game.lang
    for slot in view.crime.window:
        time = view.world.slots[slot].label.split("–")[0]
        for person in sorted(view.suspects):
            if session.game.left <= 0 or session.game.used >= limit:
                return
            text = f"{time} 你在哪？" if lang is Lang.ZH else f"Where were you at {time}?"
            session.ask(person, text)


def _solve(session: WebSession) -> None:
    game = session.game
    _everyone(session)
    pairs = [p for p in game.notebook.conflicts() if game.exposes_culprit_lie(*p)]
    first, second = pairs[0]
    session.accuse(game.case.truth.culprit, first, second)


def _solvable(lang: Lang = Lang.ZH) -> WebSession:
    """The first daily case that a sweep of the window can solve within the budget."""
    for seed in range(SEED, SEED + 50):
        session = WebSession(seed, lang)
        _everyone(session)
        game = session.game
        if any(game.exposes_culprit_lie(*p) for p in game.notebook.conflicts()):
            return WebSession(seed, lang)
    raise AssertionError("no case in 50 seeds solves this way")


# --- Session ---------------------------------------------------------------------------------


def test_a_game_runs_from_question_to_ending() -> None:
    session = _solvable()
    assert session.state().ending is None
    _solve(session)
    state = session.state()
    assert state.ending is not None
    assert state.ending.outcome == "solved"
    assert state.ending.mark.startswith("★")
    culprit = session.game.case.truth.culprit
    name = next(p.name.zh for p in session.game.case.view.world.people if p.id == culprit)
    assert name in state.ending.truth.culprit


def test_the_state_holds_no_truth_before_the_accusation() -> None:
    session = WebSession(SEED, Lang.ZH)
    _everyone(session, limit=4)
    text = to_json(session.state())
    assert '"ending": null' in text
    truth = truth_parts(session.game.case, Lang.ZH)
    assert truth.culprit not in text
    assert not [lie for lie in truth.lies if lie in text]
    assert truth.grid.places[0] not in json.loads(text)["notes"]["grid"]["places"]


def test_a_name_in_the_text_picks_the_person_and_an_empty_question_only_switches() -> None:
    session = WebSession(SEED, Lang.ZH)
    people = session.game.case.view.world.people
    target = people[0]
    session.ask("", f"{target.name.zh}：")
    assert session.current == target.id
    assert session.game.turns == []
    time = session.game.case.view.world.slots[0].label.split("–")[0]
    session.ask("", f"@{target.name.zh} {time} 你在哪？")
    assert session.game.turns[-1].addressee == target.id


def test_what_the_player_can_fix_comes_back_in_their_language() -> None:
    session = WebSession(SEED, Lang.EN)
    with pytest.raises(SessionError, match="no_addressee") as err:
        session.ask("", "where were you at 21:00?")
    assert "Choose" in err.value.text
    person = str(session.game.case.view.world.people[0].id)
    with pytest.raises(SessionError, match="too_long"):
        session.ask(person, "x" * (MAX_QUESTION + 1))
    with pytest.raises(SessionError, match="unknown_item"):
        session.check(sorted(session.game.case.view.suspects)[0], "S9", "E1")
    assert session.game.turns == []


def test_questions_stop_at_the_budget_and_one_accusation_is_all() -> None:
    session = WebSession(SEED, Lang.ZH)
    session.game.used = session.game.budget
    person = str(session.game.case.view.world.people[0].id)
    with pytest.raises(SessionError, match="game_over"):
        session.ask(person, "21:00 你在哪？")
    session = _solvable()
    _solve(session)
    with pytest.raises(SessionError, match="already_accused"):
        session.accuse(sorted(session.game.case.view.suspects)[0], "E1", "E2")


def test_the_language_changes_the_views_and_later_lines_only() -> None:
    session = WebSession(SEED, Lang.ZH)
    person = str(session.game.case.view.world.people[0].id)
    time = session.game.case.view.world.slots[0].label.split("–")[0]
    session.ask(person, f"{time} 你在哪？")
    before = session.state().turns[0].line
    session.set_lang(Lang.EN)
    state = session.state()
    assert state.lang == "en"
    assert state.turns[0].line == before  # what was said stays as it was said
    assert state.sheet.title.startswith("Loose Thread")
    assert state.turns[0].speaker == session.game.case.view.world.people[0].name.en
    session.ask(person, f"Where were you at {session.game.case.view.world.slots[1].label[:5]}?")
    assert session.state().turns[1].line.isascii()


# --- Save ------------------------------------------------------------------------------------


def test_a_save_replays_to_the_same_game_with_no_backend_call() -> None:
    session = WebSession(SEED, Lang.ZH)
    _everyone(session, limit=6)
    person = str(session.game.case.view.world.people[0].id)
    session.ask(person, "嗯……")  # free, read as nothing
    text = session.save()
    again = WebSession(SEED, Lang.ZH, read_save(text, SEED))
    assert asdict(again.state()) == asdict(session.state())
    assert again.save() == text


def test_a_save_keeps_the_ending_and_the_game_still_scores_it() -> None:
    session = _solvable()
    _solve(session)
    again, failed = open_session(session.seed, Lang.ZH, session.save())
    assert not failed
    assert asdict(again.state()) == asdict(session.state())


def test_a_bad_save_is_dropped_and_said_so() -> None:
    session = WebSession(SEED, Lang.ZH)
    _everyone(session, limit=2)
    good = session.save()
    raw = json.loads(good)
    wrong_line = json.loads(good)
    wrong_line["turns"][0]["line"] = "03:33"  # the post-check refuses it, so it cannot replay
    no_parse = json.loads(good)
    no_parse["turns"][0]["parses"] = []
    bad_kind = json.loads(good)
    bad_kind["turns"][0]["parses"][0]["kind"] = "nonsense"
    raw["version"] = 99
    for text in ("{", "[]", json.dumps(raw), json.dumps(wrong_line), json.dumps(no_parse)):
        fresh, failed = open_session(SEED, Lang.ZH, text)
        assert failed, text
        assert fresh.game.turns == []
    fresh, failed = open_session(SEED, Lang.ZH, json.dumps(bad_kind))
    assert failed
    fresh, failed = open_session(SEED + 1, Lang.ZH, good)  # another day's case
    assert failed
    assert fresh.game.turns == []


def test_a_save_cannot_claim_a_better_ending() -> None:
    session = _solvable()
    game = session.game
    wrong = next(p for p in sorted(game.case.view.suspects) if p != game.case.truth.culprit)
    _everyone(session)
    first, second = game.notebook.conflicts()[0]
    session.accuse(wrong, first, second)
    raw = json.loads(session.save())
    raw["outcome"] = "solved"
    raw["stars"] = 3
    again, _ = open_session(session.seed, Lang.ZH, json.dumps(raw))
    ending = again.state().ending
    assert ending is not None
    assert ending.outcome == "wrong"


def test_a_save_holds_neither_truth_nor_key() -> None:
    session = WebSession(SEED, Lang.ZH)
    session.use_model(_chat(_Wire(*[(200, _OK)] * 60)))
    _everyone(session, limit=3)
    assert session.game.turns
    text = session.save()
    assert FAKE_KEY not in text
    saved = read_save(text, SEED)
    assert isinstance(saved, SavedGame)
    truth = truth_parts(session.game.case, Lang.ZH)
    assert truth.culprit not in text
    assert not [lie for lie in truth.lies if lie in text]


# --- Share card ------------------------------------------------------------------------------


def _forbidden(session: WebSession) -> list[str]:
    world = session.game.case.view.world
    words: list[str] = []
    for person in world.people:
        words += [person.name.zh, person.name.en, person.role.zh, person.role.en]
        words += person.name.en.split()
    for place in world.locations:
        words += [place.name.zh, place.name.en]
    for thing in world.items:
        words += [thing.name.zh, thing.name.en]
    for slot in world.slots:
        words += slot.label.split("–")
    return words


@pytest.mark.parametrize("lang", list(Lang))
def test_the_share_card_holds_no_answer_in_any_outcome(lang: Lang) -> None:
    pattern = re.compile(
        rf"^(破绽 案件|Loose Thread case) #\d+ (★{{1,3}}|☆|✗)\n"
        rf"\d+/\d+ (问|questions)\n"
        rf"[{NOTHING_NEW}{NEW_FACT}{CONTRADICTION}]*\n?"
        rf"github\.com/JiachengWu591/loosethread$"
    )
    seen = set()
    for seed in range(SEED, SEED + 12):
        for pick in ("culprit", "innocent", "hunch"):
            session = WebSession(seed, lang)
            game = session.game
            _everyone(session)
            pairs = game.notebook.conflicts()
            if not pairs:
                continue
            truth = game.case.truth
            innocent = next(p for p in sorted(game.case.view.suspects) if p != truth.culprit)
            exposing = [p for p in pairs if game.exposes_culprit_lie(*p)]
            evidence = game.case.view.evidence
            if pick == "culprit" and exposing:
                session.accuse(truth.culprit, *exposing[0])
            elif pick == "hunch":  # two pieces of evidence never conflict, so nothing is exposed
                session.accuse(truth.culprit, evidence[0].id, evidence[1].id)
            elif pick == "innocent":
                session.accuse(innocent, *pairs[0])
            else:
                continue
            ending = session.state().ending
            assert ending is not None
            seen.add(ending.outcome)
            assert pattern.fullmatch(ending.share), ending.share
            # The link holds a surname that is also in a roster.
            words = ending.share.replace(LINK, "")
            for word in _forbidden(session):
                assert word not in words, word
    assert seen == {"solved", "hunch", "wrong"}


def test_the_squares_count_questions_on_the_budget_only() -> None:
    session = _solvable()
    person = str(session.game.case.view.world.people[0].id)
    session.ask(person, "嗯……")  # free
    _solve(session)
    game = session.game
    row = squares(game.turns)
    assert len(row) == game.used
    assert (CONTRADICTION in row) == any(t.new_conflicts for t in game.turns)
    verdict = game.verdict
    assert verdict is not None
    assert mark(verdict) == "★" * verdict.stars
    assert row in share_card(session.seed, verdict, game.turns, Lang.EN)


# --- A model in the browser ------------------------------------------------------------------


class _Wire:
    """Stands in for the network and remembers what crossed it."""

    def __init__(self, *replies: tuple[int, str]) -> None:
        self.replies, self.sent = list(replies), list[tuple[str, str, dict[str, str], str | None]]()

    def __call__(
        self, method: str, url: str, headers: Mapping[str, str], body: str | None, timeout: float
    ) -> tuple[int, str]:
        self.sent.append((method, url, dict(headers), body))
        return self.replies.pop(0)


def _chat(wire: _Wire) -> BrowserChat:
    return BrowserChat(load_backends()["deepseek"], FAKE_KEY, wire)


_OK = json.dumps(
    {
        "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    }
)


def test_the_browser_request_matches_the_config_and_the_key_stays_in_its_header() -> None:
    wire = _Wire((200, _OK))
    reply = _chat(wire).complete("sys", "user", json_mode=True, max_tokens=50)
    assert reply.text == "hello"
    assert (reply.usage.prompt_tokens, reply.usage.completion_tokens) == (7, 3)
    method, url, headers, body = wire.sent[0]
    backend = load_backends()["deepseek"]
    assert method == "POST"
    assert url == backend.base_url + "/chat/completions"
    assert headers["Authorization"] == f"Bearer {FAKE_KEY}"
    assert body is not None
    sent = json.loads(body)
    assert sent["model"] == backend.model
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["thinking"] == {"type": backend.thinking}
    assert sent["max_tokens"] == 50 + backend.reasoning_tokens
    assert FAKE_KEY not in url
    assert FAKE_KEY not in body
    assert FAKE_KEY not in repr(_chat(wire))


@pytest.mark.parametrize("status", [0, 429, 500, 503])
def test_an_unreachable_model_is_retried_as_configured_then_reported_without_its_words(
    status: int,
) -> None:
    echo = f"bad key {FAKE_KEY}"
    tries = load_backends()["deepseek"].max_retries + 1
    wire = _Wire(*[(status, echo)] * tries)
    with pytest.raises(BackendUnavailable) as err:
        _chat(wire).complete("s", "u", json_mode=False, max_tokens=5)
    assert len(wire.sent) == tries
    assert FAKE_KEY not in str(err.value)
    assert err.value.cause == f"http_{status}"


def test_a_rejected_key_is_not_retried_and_reads_as_unavailable_in_a_game() -> None:
    wire = _Wire((401, f"bad key {FAKE_KEY}"))
    with pytest.raises(BackendUnavailable) as err:
        _chat(wire).complete("s", "u", json_mode=False, max_tokens=5)
    assert len(wire.sent) == 1
    assert FAKE_KEY not in str(err.value)


def test_any_other_status_fails_closed_without_the_providers_words() -> None:
    wire = _Wire((400, f"bad request {FAKE_KEY}"))
    with pytest.raises(RuntimeError) as err:
        _chat(wire).complete("s", "u", json_mode=False, max_tokens=5)
    assert FAKE_KEY not in str(err.value)


def test_the_model_is_listed_before_first_use() -> None:
    backend = load_backends()["deepseek"]
    listed = json.dumps({"data": [{"id": backend.model}]})
    wire = _Wire((200, listed))
    _chat(wire).check_model()
    assert wire.sent[0][:2] == ("GET", backend.base_url + "/models")
    with pytest.raises(ModelMissing):
        _chat(_Wire((200, json.dumps({"data": [{"id": "other"}]})))).check_model()
    with pytest.raises(KeyRejected):
        _chat(_Wire((401, "no"))).check_model()


# --- Bridge ----------------------------------------------------------------------------------


def _reply(text: str) -> dict[str, object]:
    reply: dict[str, object] = json.loads(text)
    return reply


def test_connecting_reports_each_failure_and_leaves_the_game_as_it_was() -> None:
    backend = load_backends()["deepseek"]
    first = _reply(bridge.start(SEED, "zh", ""))
    assert first["error"] == ""
    assert _reply(bridge.connect("  "))["error"] == "key_empty"
    for wire, code in (
        (_Wire((401, f"no {FAKE_KEY}")), "key_rejected"),
        (_Wire((200, json.dumps({"data": []}))), "model_missing"),
        (_Wire((0, ""), (0, "")), "model_unreachable"),
        (_Wire((200, "not json")), "internal:JSONDecodeError"),
    ):
        reply = bridge.connect(FAKE_KEY, wire)
        assert _reply(reply)["error"] == code
        assert FAKE_KEY not in reply
    wire = _Wire((200, json.dumps({"data": [{"id": backend.model}]})))
    reply = bridge.connect(FAKE_KEY, wire)
    state = _reply(reply)["state"]
    assert isinstance(state, dict)
    assert state["mode"] == "model"
    assert FAKE_KEY not in reply
    state = _reply(bridge.disconnect())["state"]
    assert isinstance(state, dict)
    assert state["mode"] == "rules"


def test_a_failed_model_call_costs_nothing_and_the_reply_never_holds_the_key() -> None:
    bridge.start(SEED, "zh", "")
    backend = load_backends()["deepseek"]
    wire = _Wire((200, json.dumps({"data": [{"id": backend.model}]})))
    wire.replies += [(401, f"bad {FAKE_KEY}")] * 4
    bridge.connect(FAKE_KEY, wire)
    person = str(daily_case(SEED).case.view.world.people[0].id)
    reply = bridge.ask(person, "21:00 你在哪？")
    assert FAKE_KEY not in reply
    state = _reply(reply)["state"]
    assert isinstance(state, dict)
    assert state["used"] == 0
    assert len(wire.sent) == 2  # one list, one call: the writer is not tried after that


def test_an_unexpected_failure_is_reported_by_its_type_only() -> None:
    bridge.start(SEED, "zh", "")
    reply = _reply(bridge.set_lang("klingon"))
    assert reply["error"] == "internal:ValueError"
    assert reply["message"] == ""
    assert reply["state"] is None


def test_restoring_says_when_a_save_was_dropped() -> None:
    assert _reply(bridge.start(SEED, "zh", "{"))["restore_failed"] is True
    assert _reply(bridge.start(SEED, "zh", ""))["restore_failed"] is False


# --- Build and page --------------------------------------------------------------------------


def test_the_bundle_leaves_out_what_a_browser_cannot_or_need_not_run() -> None:
    names = {name for _, name in bundled_files()}
    assert "loosethread/web/bridge.py" in names
    assert "loosethread/llm/backends.toml" in names
    assert "loosethread/content/mistpine.json" in names
    assert "loosethread/llm/client.py" not in names
    assert not {n for n in names if "/study/" in n or "/site/" in n or "__pycache__" in n}


def test_the_bundle_is_the_same_bytes_on_every_build(tmp_path: Path) -> None:
    pack_package(tmp_path / "a.zip")
    pack_package(tmp_path / "b.zip")
    assert (tmp_path / "a.zip").read_bytes() == (tmp_path / "b.zip").read_bytes()


def test_the_page_side_runs_without_openai() -> None:
    code = (
        "import sys; sys.modules['openai'] = None\n"
        "import loosethread.web.bridge, loosethread.web.session\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=120)


def test_the_web_package_uses_only_the_standard_library() -> None:
    allowed = set(sys.stdlib_module_names) | {"loosethread", "js"}
    for path in (Path(loosethread.__file__).parent / "web").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert {a.name.split(".")[0] for a in node.names} <= allowed, path
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                assert node.module.split(".")[0] in allowed, path


def _page_code() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(SITE.iterdir())
        if path.suffix in (".js", ".mjs", ".html")
    )


def test_the_page_cannot_write_a_key_or_a_line_where_it_should_not() -> None:
    """A text check of the page's code. It cannot see a leak by some other route; D-044 records the
    browser run that looks at the requests, the storage and the console."""
    code = _page_code()
    assert code
    assert "innerHTML" not in code  # every line a model wrote is set as text
    assert "console." not in code
    assert "document.cookie" not in code
    assert "sessionStorage" not in code
    assert "location.search =" not in code
    storing = [line for line in code.splitlines() if "localStorage" in line]
    assert storing, "the page keeps progress in localStorage"
    assert not [line for line in storing if re.search(r"key\b|apikey|token", line, re.I)]


def test_a_save_that_names_an_unknown_person_is_dropped() -> None:
    session = WebSession(SEED, Lang.ZH)
    _everyone(session, limit=2)
    raw = json.loads(session.save())
    raw["turns"][0]["addressee"] = "nobody"
    fresh, failed = open_session(SEED, Lang.ZH, json.dumps(raw))
    assert failed
    assert fresh.game.turns == []
