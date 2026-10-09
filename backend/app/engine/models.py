from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    description: str
    goes: str
    move_label: str
    connections: tuple[str, ...]


@dataclass
class Goal:
    """A pursuit the engine can finish from world state.

    `condition` is a key in the engine's completion table, not a sentence.
    `threshold` is the number that condition compares against.
    """

    id: str
    kind: str
    status: str
    label: str
    condition: str
    threshold: int = 0


@dataclass
class Character:
    id: str
    name: str
    role: str
    is_player: bool
    location_id: str
    fatigue: int
    current_action: str
    action_target: str | None
    traits: list[str]
    schedule: dict[str, Any]
    goals: list[Goal] = field(default_factory=list)
    carried_parts: int = 0
    # Last parts exchange with Marek: "", "refused", or "handover".
    # A refusal blocks the same request until his accept check would pass.
    parts_result: str = ""


@dataclass
class WorldState:
    game_time: datetime
    seed: int
    rng_counter: int
    threat_level: int
    grid_condition: int
    market_stock: int
    workshop_parts: int
    tick_count: int
    last_real_time: datetime | None
    characters: dict[str, Character]

    @property
    def player(self) -> Character:
        for character in self.characters.values():
            if character.is_player:
                return character
        raise RuntimeError("player is missing")


@dataclass
class GameEvent:
    game_time: datetime
    kind: str
    message: str
    actor_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionCandidate:
    action_id: str
    score: int
    target: str | None = None
    reason: str = ""
    target_character_id: str | None = None


@dataclass(frozen=True)
class DialogueTurn:
    npc_id: str
    npc_name: str
    line: str
    options: list[dict[str, str]]
