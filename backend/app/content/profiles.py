from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Acquaintance(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    note: str = ""


class CharacterProfile(BaseModel):
    """Static extension of a character row.

    Name, role, traits, and engine goals stay on the character record.
    This file adds biography and private material that the row does not have.
    Stock, fatigue, parts, and the goal the engine is running are not copied
    here. Another resident is another JSON file in this folder: speech ``llm``
    selects the same dialogue path. No second engine.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    speech: str = "template"
    age: int | None = None
    biography: str = ""
    biography_status: str = ""
    social_position: str = ""
    habits: list[str] = Field(default_factory=list)
    fears: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    speech_manner: str = ""
    desires: list[str] = Field(default_factory=list)
    desires_short: list[str] = Field(default_factory=list)
    desires_long: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    withheld: list[str] = Field(default_factory=list)
    reveal_conditions: list[str] = Field(default_factory=list)
    attitude_to_player: str = ""
    acquaintances: list[Acquaintance] = Field(default_factory=list)
    social_preferences: list[str] = Field(default_factory=list)
    knows: list[str] = Field(default_factory=list)
    event_stance: str = ""
    # Applied only beside a witnessed event of that kind. Not a claim the event happened.
    event_readings: dict[str, str] = Field(default_factory=dict)


def profiles_dir() -> Path:
    return Path(__file__).resolve().parent / "profiles"


def load_profiles(directory: Path | None = None) -> dict[str, CharacterProfile]:
    root = directory or profiles_dir()
    loaded: dict[str, CharacterProfile] = {}
    if not root.exists():
        return loaded
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        profile = CharacterProfile.model_validate(payload)
        loaded[profile.id] = profile
    return loaded
