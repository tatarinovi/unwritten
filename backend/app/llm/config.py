from __future__ import annotations

import os
from dataclasses import dataclass

# Hugging Face repo id. This is not an Ollama tag. Point UNWRITTEN_LLM_MODEL
# at the local tag after the GGUF is imported. The game does not download it.
DEFAULT_MODEL = (
    "DavidAU/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP-GGUF"
)


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    context: int
    temperature: float
    timeout_seconds: float


def load_settings() -> LLMSettings:
    context = int(os.environ.get("UNWRITTEN_LLM_CONTEXT", "16384"))
    temperature = float(os.environ.get("UNWRITTEN_LLM_TEMPERATURE", "0.7"))
    timeout = float(os.environ.get("UNWRITTEN_LLM_TIMEOUT", "60"))
    if context < 1:
        context = 16384
    if timeout <= 0:
        timeout = 60
    return LLMSettings(
        base_url=os.environ.get("UNWRITTEN_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        model=os.environ.get("UNWRITTEN_LLM_MODEL", DEFAULT_MODEL),
        context=context,
        temperature=temperature,
        timeout_seconds=timeout,
    )
