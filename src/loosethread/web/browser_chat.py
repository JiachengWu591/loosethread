"""A model reached from the browser with a key of the player's own (CP-11, D-043).

The `openai` package cannot run in Pyodide, so this sends the same request by hand. Base URL, model
name, thinking mode and retries all come from `backends.toml`, and the models are listed before
first use, as with `OpenAIChat`.

The key goes in one place, the Authorization header. It is not in `repr`, an exception or a URL. A
provider's reply to a failed call is never read, because it may echo the key: only the status is
kept.
"""

import json
import time
from collections.abc import Callable, Mapping

from loosethread.llm.chat import Completion
from loosethread.llm.config import Backend
from loosethread.npc import BackendUnavailable, Usage

type Send = Callable[[str, str, Mapping[str, str], str | None, float], tuple[int, str]]

_RETRY = frozenset({0, 408, 409, 429})  # 0: no response at all


class KeyRejected(RuntimeError):
    """The provider refused this key."""


class ModelMissing(RuntimeError):
    """The provider does not list the configured model."""


def xhr_send(
    method: str, url: str, headers: Mapping[str, str], body: str | None, timeout: float
) -> tuple[int, str]:
    """A blocking request, which a browser allows only in a worker. `js` exists only in Pyodide."""
    from js import XMLHttpRequest  # type: ignore[import-not-found]  # noqa: PLC0415

    request = XMLHttpRequest.new()
    request.open(method, url, False)
    request.timeout = int(timeout * 1000)
    try:
        for name, value in headers.items():
            request.setRequestHeader(name, value)
        request.send(body)
    except Exception:  # a network failure, a timeout or a key a header cannot hold: no response
        return 0, ""
    return int(request.status), str(request.responseText)


class BrowserChat:
    def __init__(self, backend: Backend, key: str, send: Send, temperature: float = 0.0) -> None:
        self.backend, self.temperature = backend, temperature
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self._send = send

    def __repr__(self) -> str:
        return f"BrowserChat({self.backend.name!r})"

    def _request(self, method: str, path: str, body: str | None) -> str:
        url = self.backend.base_url.rstrip("/") + path
        status = 0
        unreachable = True
        for _ in range(self.backend.max_retries + 1):
            status, text = self._send(method, url, self._headers, body, self.backend.timeout)
            if status == 200:
                return text
            unreachable = status in _RETRY or status >= 500
            if not unreachable:
                break
        if status in (401, 403):
            raise KeyRejected(f"http_{status}")
        if unreachable:
            raise BackendUnavailable(f"http_{status}")
        raise RuntimeError(f"http_{status}")

    def models(self) -> tuple[str, ...]:
        reply = json.loads(self._request("GET", "/models", None))
        return tuple(sorted(str(m["id"]) for m in reply["data"]))

    def check_model(self) -> None:
        if self.backend.model not in self.models():
            raise ModelMissing(self.backend.name)

    def complete(self, system: str, user: str, *, json_mode: bool, max_tokens: int) -> Completion:
        thinking = self.backend.thinking
        body: dict[str, object] = {
            "model": self.backend.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,  # DeepSeek ignores it while thinking
            "max_tokens": max_tokens + self.backend.reasoning_tokens,
            "response_format": {"type": "json_object" if json_mode else "text"},
        }
        if thinking:
            body["thinking"] = {"type": thinking}
        start = time.perf_counter()
        try:
            text = self._request("POST", "/chat/completions", json.dumps(body, ensure_ascii=False))
        except KeyRejected as exc:  # mid-game this reads as "ask again", at no cost
            raise BackendUnavailable(str(exc)) from None
        seconds = time.perf_counter() - start
        reply = json.loads(text)
        choice = reply["choices"][0]
        used = reply.get("usage") or {}
        usage = Usage(
            calls=1,
            prompt_tokens=int(used.get("prompt_tokens", 0)),
            completion_tokens=int(used.get("completion_tokens", 0)),
            seconds=seconds,
        )
        return Completion(
            str(choice["message"].get("content") or ""),
            usage,
            str(choice.get("finish_reason") or ""),
        )
