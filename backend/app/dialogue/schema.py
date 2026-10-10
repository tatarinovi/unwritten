from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm.errors import LLMFailure, USER_MESSAGES


class NpcReply(BaseModel):
    """The only object the model is allowed to return."""

    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1, max_length=2000)


def parse_npc_reply(raw: str) -> str:
    payload = _load_object(raw)
    try:
        parsed = NpcReply.model_validate(payload)
    except ValidationError as exc:
        raise LLMFailure("invalid_json", USER_MESSAGES["invalid_json"]) from exc
    line = parsed.reply.strip()
    if not line:
        raise LLMFailure("empty_reply", USER_MESSAGES["empty_reply"])
    return line


def _load_object(raw: str) -> object:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise LLMFailure("invalid_json", USER_MESSAGES["invalid_json"])
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMFailure("invalid_json", USER_MESSAGES["invalid_json"]) from exc
