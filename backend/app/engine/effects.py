from __future__ import annotations

from typing import Any

from app.engine.models import Character, GameEvent, Location, WorldState


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def make_event(
    world: WorldState,
    kind: str,
    message: str,
    actor_id: str | None,
    data: dict[str, Any] | None = None,
) -> GameEvent:
    return GameEvent(
        game_time=world.game_time,
        kind=kind,
        message=message,
        actor_id=actor_id,
        data=dict(data or {}),
    )


def apply_rest(npc: Character, world: WorldState) -> GameEvent:
    if npc.fatigue >= 70:
        message = f"{npc.name} отдыхает: сил почти не осталось."
    else:
        message = f"{npc.name} отдыхает."
    npc.fatigue = clamp(npc.fatigue - 22)
    npc.current_action = "rest"
    npc.action_target = None
    return make_event(world, "npc_rest", message, npc.id)


def apply_observe(npc: Character, world: WorldState, locations: dict[str, Location]) -> GameEvent:
    place = locations[npc.location_id].name
    npc.fatigue = clamp(npc.fatigue + 1)
    npc.current_action = "observe"
    npc.action_target = None
    return make_event(world, "npc_observe", f"{npc.name} наблюдает. Место: «{place}».", npc.id)


def apply_travel(
    npc: Character,
    world: WorldState,
    locations: dict[str, Location],
    target: str,
    reason: str,
) -> GameEvent:
    origin = npc.location_id
    npc.location_id = target
    npc.current_action = "travel"
    npc.action_target = target
    npc.fatigue = clamp(npc.fatigue + 4)
    destination = locations[target]
    return make_event(
        world,
        "npc_move",
        f"{npc.name} идёт {destination.goes}.",
        npc.id,
        {"from": origin, "to": target, "reason": reason},
    )
