from __future__ import annotations

from typing import Protocol

from app.engine.effects import apply_observe, apply_rest, apply_travel
from app.engine.goals import interaction_allowed
from app.engine.models import ActionCandidate, Character, GameEvent, Location, WorldState
from app.engine.rng import CounterRNG


class Behavior(Protocol):
    def candidates(self, npc: Character, world: WorldState) -> list[ActionCandidate]: ...

    def precondition(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> bool: ...

    def apply(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> list[GameEvent]: ...


def choose_action(candidates: list[ActionCandidate], rng: CounterRNG) -> ActionCandidate:
    """Highest score wins. Ties break on a seeded roll, then on action id.

    The roll is smaller than 1, so it never overturns a score gap of 1 or more.
    Every candidate consumes one draw, in a stable order, so seeds stay aligned.
    """
    best: ActionCandidate | None = None
    best_key: tuple[int, float, str, str, str] | None = None
    ordered = sorted(
        candidates,
        key=lambda item: (item.action_id, item.target or "", item.target_character_id or "", item.reason),
    )
    for candidate in ordered:
        roll = rng.random()
        key = (
            candidate.score,
            roll,
            candidate.action_id,
            candidate.target or "",
            candidate.target_character_id or "",
        )
        if best is None or best_key is None or key > best_key:
            best = candidate
            best_key = key
    if best is None:
        raise RuntimeError("no candidate")
    return best


def run_npc_tick(
    world: WorldState,
    behaviors: dict[str, Behavior],
    locations: dict[str, Location],
    rng: CounterRNG,
) -> list[GameEvent]:
    events: list[GameEvent] = []
    npcs = sorted(
        (character for character in world.characters.values() if not character.is_player),
        key=lambda character: character.id,
    )
    for npc in npcs:
        behavior = behaviors[npc.id]
        valid = [
            candidate
            for candidate in behavior.candidates(npc, world)
            if _candidate_allowed(behavior, npc, world, candidate, locations)
        ]
        if not valid:
            continue
        chosen = choose_action(valid, rng)
        before = npc.location_id
        produced = behavior.apply(npc, world, chosen, locations)
        if npc.location_id != before:
            moves = [event for event in produced if event.kind == "npc_move" and event.actor_id == npc.id]
            if len(moves) != 1 or moves[0].data.get("to") != npc.location_id:
                raise RuntimeError("location changed without a resolved move")
        events.extend(produced)
    return events


def _candidate_allowed(
    behavior: Behavior,
    npc: Character,
    world: WorldState,
    action: ActionCandidate,
    locations: dict[str, Location],
) -> bool:
    if action.target_character_id is not None and not interaction_allowed(npc, world, action.target_character_id):
        return False
    return behavior.precondition(npc, world, action, locations)


class NpcBehavior:
    """Shared physical checks: rest, observe, and one-step travel."""

    def precondition(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> bool:
        if action.action_id in {"rest", "observe"}:
            return True
        if action.action_id == "travel":
            target = action.target
            if not target or target == npc.location_id or target not in locations:
                return False
            current = locations.get(npc.location_id)
            return current is not None and target in current.connections
        return False

    def apply(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> list[GameEvent]:
        if action.action_id == "rest":
            return [apply_rest(npc, world)]
        if action.action_id == "observe":
            return [apply_observe(npc, world, locations)]
        if action.action_id == "travel":
            if action.target is None:
                raise RuntimeError("travel without a target")
            return [apply_travel(npc, world, locations, action.target, action.reason)]
        raise RuntimeError(f"unhandled action {action.action_id}")
