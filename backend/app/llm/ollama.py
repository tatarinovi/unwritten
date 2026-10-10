from __future__ import annotations

import time

import httpx

from app.llm.config import LLMSettings
from app.llm.errors import LLMFailure, USER_MESSAGES
from app.llm.protocol import LLMCompletion


class OllamaClient:
    """Local Ollama over HTTP. Holds no game state and applies no world changes."""

    def __init__(self, settings: LLMSettings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport

    def complete(self, *, system: str, user: str) -> LLMCompletion:
        started = time.perf_counter()
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.settings.temperature,
                "num_ctx": self.settings.context,
            },
        }
        try:
            with httpx.Client(timeout=self.settings.timeout_seconds, transport=self._transport) as client:
                response = client.post(f"{self.settings.base_url}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMFailure("timeout", USER_MESSAGES["timeout"]) from exc
        except httpx.HTTPError as exc:
            raise LLMFailure("server_down", USER_MESSAGES["server_down"]) from exc
        self._raise_for_status(response)
        try:
            body = response.json()
            content = body["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMFailure("invalid_json", USER_MESSAGES["invalid_json"]) from exc
        if not isinstance(content, str):
            raise LLMFailure("invalid_json", USER_MESSAGES["invalid_json"])
        elapsed = int((time.perf_counter() - started) * 1000)
        model = body.get("model") if isinstance(body, dict) else None
        return LLMCompletion(
            text=content,
            model=str(model or self.settings.model),
            latency_ms=elapsed,
        )

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail = response.text.lower()
        if response.status_code == 404 or "not found" in detail or "unknown model" in detail:
            raise LLMFailure("unknown_model", USER_MESSAGES["unknown_model"])
        raise LLMFailure("server_down", USER_MESSAGES["server_down"])
