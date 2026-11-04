"""The chat contract on its own, so that the browser build can use it without `openai`."""

from dataclasses import dataclass
from typing import Protocol

from loosethread.npc import Usage


@dataclass(frozen=True)
class Completion:
    text: str
    usage: Usage
    finish_reason: str  # "stop", "length", ...


class ChatModel(Protocol):
    def complete(self, system: str, user: str, *, json_mode: bool, max_tokens: int) -> Completion:
        """One chat turn. Raises `BackendUnavailable` if the model cannot be reached, and other
        exceptions on other provider errors."""
        ...
