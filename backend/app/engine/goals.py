from __future__ import annotations

import json
from typing import Any

from app.engine.models import Character, Goal, WorldState

UNRESOLVED_LEGACY = "unresolved_legacy"
LONG_TERM = "long_term"
SHORT_TERM = "short_term"
ACTIVE = "active"
COMPLETED = "completed"


def condition_met(world: WorldState, goal: Goal) -> bool:
    """Completion is a fact about the world, never a phrase in the log."""
    if goal.condition == "workshop_parts_at_least":
        return world.workshop_parts >= goal.threshold
    if goal.condition == "threat_at_most":
        return world.threat_level <= goal.threshold
    if goal.condition == "market_stock_at_least":
        return world.market_stock >= goal.threshold
    if goal.condition == "grid_at_least":
        return world.grid_condition >= goal.threshold
    return False


def evaluate_goals(world: WorldState) -> None:
    for character in world.characters.values():
        for goal in character.goals:
            if goal.status != ACTIVE:
                continue
            if condition_met(world, goal):
                goal.status = COMPLETED


def has_active_goal(character: Character, goal_id: str) -> bool:
    return any(goal.id == goal_id and goal.status == ACTIVE for goal in character.goals)


def ensure_active_goal(character: Character, template: Goal) -> bool:
    """Add `template` when this character has no active goal with that id.

    Completed copies stay in the list. A repeated cause does not stack another
    active row.
    """
    if has_active_goal(character, template.id):
        return False
    character.goals.append(
        Goal(
            id=template.id,
            kind=template.kind,
            status=ACTIVE,
            label=template.label,
            condition=template.condition,
            threshold=template.threshold,
        )
    )
    return True


def display_goal(character: Character) -> str:
    """Russian label: an active short-term goal, otherwise the long-term one."""
    active = [goal for goal in character.goals if goal.status == ACTIVE]
    short = [goal for goal in active if goal.kind == SHORT_TERM]
    if short:
        return short[0].label
    long = [goal for goal in active if goal.kind == LONG_TERM]
    if long:
        return long[0].label
    if active:
        return active[0].label
    if character.goals:
        return character.goals[0].label
    return ""


def goal_payload(goal: Goal) -> dict[str, Any]:
    return {
        "id": goal.id,
        "kind": goal.kind,
        "status": goal.status,
        "label": goal.label,
        "condition": goal.condition,
        "threshold": goal.threshold,
    }


def dump_goals(goals: list[Goal]) -> str:
    return json.dumps([goal_payload(goal) for goal in goals], ensure_ascii=False)


def legacy_placeholder(label: str) -> Goal:
    return Goal(
        id="legacy",
        kind=LONG_TERM,
        status=ACTIVE,
        label=label,
        condition=UNRESOLVED_LEGACY,
        threshold=0,
    )


def parse_stored_goals(raw: str) -> list[Goal]:
    """Load structured goals. A pre-v0.0.2 plain string becomes a placeholder.

    Content replaces that placeholder with the character's long-term goal.
    """
    text = (raw or "").strip()
    if text.startswith("["):
        payload = json.loads(text)
        goals: list[Goal] = []
        for item in payload:
            goals.append(
                Goal(
                    id=str(item["id"]),
                    kind=str(item["kind"]),
                    status=str(item["status"]),
                    label=str(item["label"]),
                    condition=str(item["condition"]),
                    threshold=int(item.get("threshold", 0)),
                )
            )
        return goals
    return [legacy_placeholder(text)]


def interaction_allowed(actor: Character, world: WorldState, target_id: str | None) -> bool:
    """NPC-to-NPC actions require a real, present, other character.

    The player is not a target of these actions. Location is the availability
    check: there is no separate exclusive-action lock. Apart means the action
    is illegal, so callers must not move resources.
    """
    if not target_id or target_id == actor.id:
        return False
    target = world.characters.get(target_id)
    if target is None or target.is_player:
        return False
    return target.location_id == actor.location_id
