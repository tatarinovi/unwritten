from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMCompletion:
    text: str
    model: str
    latency_ms: int


class LLMClient(Protocol):
    """One completion. Game rules depend on this shape, not on a vendor.

    An OpenAI-compatible client can implement the same method later.
    Every conversational NPC uses this one client. v0.0.3.1 ships Ollama.
    """

    def complete(self, *, system: str, user: str) -> LLMCompletion: ...
