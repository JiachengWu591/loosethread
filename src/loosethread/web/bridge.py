"""What the page's worker calls. Every function takes plain values and returns one JSON reply.

An unexpected failure is reported by its type alone, as a message could carry a provider's words.
"""

from collections.abc import Callable
from dataclasses import dataclass

from loosethread.llm.config import load_backends
from loosethread.model import Lang
from loosethread.npc import BackendUnavailable
from loosethread.web.browser_chat import BrowserChat, KeyRejected, ModelMissing, Send, xhr_send
from loosethread.web.session import (
    BACKEND,
    Check,
    SessionError,
    State,
    WebSession,
    open_session,
    to_json,
)

_session: WebSession | None = None


@dataclass(frozen=True)
class Reply:
    state: State | None = None  # none on an error, which changes nothing
    save: str = ""
    error: str = ""  # a code for the page
    message: str = ""  # already in the player's language, when it comes from the game
    check: Check | None = None
    restore_failed: bool = False


def _current() -> WebSession:
    if _session is None:
        raise RuntimeError("no session")
    return _session


def _done(check_result: Check | None = None, restore_failed: bool = False) -> str:
    session = _current()
    return to_json(Reply(session.state(), session.save(), "", "", check_result, restore_failed))


def _guarded(act: Callable[[], str]) -> str:
    try:
        return act()
    except SessionError as err:
        return to_json(Reply(error=err.code, message=err.text))
    except Exception as err:
        return to_json(Reply(error=f"internal:{type(err).__name__}"))


def start(seed: int, lang: str, saved: str, hints: bool = True) -> str:
    def act() -> str:
        global _session
        _session, failed = open_session(seed, Lang(lang), saved, hints)
        return _done(restore_failed=failed)

    return _guarded(act)


def set_hints(on: bool) -> str:
    def act() -> str:
        _current().set_hints(on)
        return _done()

    return _guarded(act)


def set_lang(lang: str) -> str:
    def act() -> str:
        _current().set_lang(Lang(lang))
        return _done()

    return _guarded(act)


def ask(person: str, text: str) -> str:
    def act() -> str:
        _current().ask(person, text)
        return _done()

    return _guarded(act)


def check(suspect: str, first: str, second: str) -> str:
    def act() -> str:
        return _done(_current().check(suspect, first, second))

    return _guarded(act)


def accuse(suspect: str, first: str, second: str) -> str:
    def act() -> str:
        _current().accuse(suspect, first, second)
        return _done()

    return _guarded(act)


def connect(key: str, send: Send = xhr_send) -> str:
    """Use a model with the player's key. On any failure the game stays as it was."""

    def act() -> str:
        if not key.strip():
            return to_json(Reply(error="key_empty"))
        chat = BrowserChat(load_backends()[BACKEND], key.strip(), send)
        try:
            chat.check_model()
        except KeyRejected:
            return to_json(Reply(error="key_rejected"))
        except ModelMissing:
            return to_json(Reply(error="model_missing"))
        except BackendUnavailable:
            return to_json(Reply(error="model_unreachable"))
        _current().use_model(chat)
        return _done()

    return _guarded(act)


def disconnect() -> str:
    def act() -> str:
        _current().use_rules()
        return _done()

    return _guarded(act)
