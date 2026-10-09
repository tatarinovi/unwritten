from __future__ import annotations

from app.engine.goals import ACTIVE, LONG_TERM, SHORT_TERM
from app.engine.models import Goal

SECURITY_ID = "security"
PROFIT_ID = "profit"
GRID_ID = "grid"
OBTAIN_PARTS_ID = "obtain_parts"
ORDINARY_DAY_ID = "ordinary_day"


def ordinary_day_goal() -> Goal:
    # Threat never drops below 0, so this stays active for the resident.
    return Goal(
        id=ORDINARY_DAY_ID,
        kind=LONG_TERM,
        status=ACTIVE,
        label="Прожить обычный день",
        condition="threat_at_most",
        threshold=-1,
    )


def security_goal() -> Goal:
    return Goal(
        id=SECURITY_ID,
        kind=LONG_TERM,
        status=ACTIVE,
        label="Безопасность поселения",
        condition="threat_at_most",
        threshold=0,
    )


def profit_goal() -> Goal:
    return Goal(
        id=PROFIT_ID,
        kind=LONG_TERM,
        status=ACTIVE,
        label="Прибыль",
        condition="market_stock_at_least",
        threshold=100,
    )


def grid_goal() -> Goal:
    return Goal(
        id=GRID_ID,
        kind=LONG_TERM,
        status=ACTIVE,
        label="Держать энергосеть",
        condition="grid_at_least",
        threshold=100,
    )


def obtain_parts_goal() -> Goal:
    # Finishes only when parts are in the workshop, not when she asks.
    return Goal(
        id=OBTAIN_PARTS_ID,
        kind=SHORT_TERM,
        status=ACTIVE,
        label="Достать детали для сети",
        condition="workshop_parts_at_least",
        threshold=1,
    )


def legacy_long_term(character_id: str, label: str) -> Goal:
    """Turn a v0.0.1 goal string into that character's long-term goal."""
    factories = {
        "player": ordinary_day_goal,
        "ivar": security_goal,
        "marek": profit_goal,
        "eyra": grid_goal,
    }
    factory = factories.get(character_id)
    if factory is not None:
        return factory()
    return Goal(
        id=f"legacy_{character_id}",
        kind=LONG_TERM,
        status=ACTIVE,
        label=label or "Цель",
        condition="threat_at_most",
        threshold=-1,
    )
