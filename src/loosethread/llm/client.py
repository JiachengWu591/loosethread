"""OpenAI-compatible chat client for DeepSeek and llama.cpp.

The API key is read from the environment variable the backend names and handed to the client; it
is never stored on our objects, printed or logged. Callers that record a failure record only the
exception type, because provider error messages may echo part of the key.
"""

import os
import time
from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONObject, ResponseFormatText

from loosethread.llm.config import Backend, load_backends
from loosethread.npc import Usage


@dataclass(frozen=True)
class Completion:
    text: str
    usage: Usage
    finish_reason: str  # "stop", "length", ...


class ChatModel(Protocol):
    def complete(self, system: str, user: str, *, json_mode: bool, max_tokens: int) -> Completion:
        """One chat turn. Raises on transport or provider errors."""
        ...


class MissingKey(RuntimeError):
    """The environment variable that should hold the API key is not set."""


class OpenAIChat:
    def __init__(self, backend: Backend, temperature: float = 0.0) -> None:
        key = os.environ.get(backend.api_key_env, "") if backend.api_key_env else "none"
        if not key:
            raise MissingKey(f"environment variable {backend.api_key_env} is not set")
        self.backend, self.temperature = backend, temperature
        self._client = OpenAI(
            api_key=key,
            base_url=backend.base_url,
            timeout=backend.timeout,
            max_retries=backend.max_retries,
        )

    def models(self) -> tuple[str, ...]:
        return tuple(sorted(m.id for m in self._client.models.list()))

    def check_model(self) -> None:
        """Fail unless the configured model is among the ones the server lists."""
        served = self.models()
        if self.backend.model not in served:
            raise RuntimeError(
                f"[{self.backend.name}] model {self.backend.model!r} is not served; "
                f"the server lists {list(served)}"
            )

    def complete(self, system: str, user: str, *, json_mode: bool, max_tokens: int) -> Completion:
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        fmt: ResponseFormatJSONObject | ResponseFormatText
        fmt = {"type": "json_object"} if json_mode else {"type": "text"}
        thinking = self.backend.thinking
        start = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self.backend.model,
            messages=messages,
            temperature=self.temperature,  # DeepSeek ignores it while thinking
            max_tokens=max_tokens + self.backend.reasoning_tokens,
            response_format=fmt,
            extra_body={"thinking": {"type": thinking}} if thinking else None,
        )
        seconds = time.perf_counter() - start
        choice = response.choices[0]
        used = response.usage
        usage = Usage(
            calls=1,
            prompt_tokens=used.prompt_tokens if used else 0,
            completion_tokens=used.completion_tokens if used else 0,
            seconds=seconds,
        )
        return Completion(choice.message.content or "", usage, choice.finish_reason or "")


def open_model(name: str) -> OpenAIChat:
    """The configured backend `name`, after checking that its model is served."""
    backends = load_backends()
    if name not in backends:
        raise KeyError(f"no backend {name!r}; configured: {sorted(backends)}")
    model = OpenAIChat(backends[name])
    model.check_model()
    return model
