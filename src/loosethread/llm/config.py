"""Backend settings, read from `backends.toml`."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from loosethread.npc import Usage

CONFIG = Path(__file__).with_name("backends.toml")


@dataclass(frozen=True)
class Backend:
    name: str
    base_url: str
    model: str
    api_key_env: str  # name of the environment variable holding the key; "" for none
    price_input: float  # CNY per 1M input tokens: peak price, cache miss (an upper bound)
    price_output: float  # CNY per 1M output tokens: peak price
    timeout: float  # seconds per request
    max_retries: int
    thinking: str = ""  # DeepSeek thinking mode, "enabled" or "disabled"; "" sends nothing
    reasoning_tokens: int = 0  # added to every call's max_tokens: hidden reasoning counts there

    def cost(self, usage: Usage) -> float:
        """Upper bound of what `usage` cost, in CNY."""
        spent = usage.prompt_tokens * self.price_input + usage.completion_tokens * self.price_output
        return spent / 1_000_000


def load_backends(path: Path = CONFIG) -> dict[str, Backend]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    backends: dict[str, Backend] = {}
    for name, table in raw.items():
        if not isinstance(table, dict):
            raise ValueError(f"{path.name}: [{name}] must be a table")
        try:
            backend = Backend(
                name=name,
                base_url=str(table["base_url"]),
                model=str(table["model"]),
                api_key_env=str(table["api_key_env"]),
                price_input=float(table["price_input"]),
                price_output=float(table["price_output"]),
                timeout=float(table["timeout"]),
                max_retries=int(table["max_retries"]),
                thinking=str(table.get("thinking", "")),
                reasoning_tokens=int(table.get("reasoning_tokens", 0)),
            )
        except KeyError as missing:
            raise ValueError(f"{path.name}: [{name}] lacks {missing}") from None
        if backend.price_input < 0 or backend.price_output < 0 or backend.timeout <= 0:
            raise ValueError(f"{path.name}: [{name}] has a negative price or no timeout")
        if backend.thinking not in ("", "enabled", "disabled") or backend.reasoning_tokens < 0:
            raise ValueError(f"{path.name}: [{name}] has a bad thinking setting")
        backends[name] = backend
    return backends
