from __future__ import annotations

from app.content.behaviors import EyraBehavior, IvarBehavior, MarekBehavior
from app.content.dialogue_lines import dialogue_bundle as build_dialogue_bundle
from app.content.goals import (
    grid_goal,
    legacy_long_term,
    obtain_parts_goal,
    ordinary_day_goal,
    profit_goal,
    security_goal,
)
from app.engine.goals import UNRESOLVED_LEGACY, ensure_active_goal
from app.engine.models import Character, Location, WorldState
from app.engine.npc import Behavior
from app.engine.rng import CounterRNG
from app.engine.timekeep import GAME_START

LOCATION_ORDER = ("city_gates", "market", "workshop")

_RAW_LOCATIONS = {
    "city_gates": (
        "Городские ворота",
        "Бетонная арка на въезде в Узел-17. Шлагбаум, дежурная будка, камеры на серых кронштейнах. За периметром — служебная дорога и сухой пустырь. Пахнет пылью и холодным металлом.",
        "к городским воротам",
        "Идти к городским воротам",
    ),
    "market": (
        "Торговая площадь",
        "Крытый проход между цехами: ларьки, ящики с деталями, термосы с чаем. На табло над рядами — время и цена меди. Здесь вполголоса решают, у кого сегодня есть нужная запчасть.",
        "на торговую площадь",
        "Идти на торговую площадь",
    ),
    "workshop": (
        "Мастерская",
        "Низкий цех энергоучастка. Щиты, кабель-каналы, запах тёплой изоляции. На стене схема сети Узла-17, несколько участков помечены мелом. Верстак заставлен разобранными блоками.",
        "в мастерскую",
        "Идти в мастерскую",
    ),
}

ACTION_LABELS = {
    "idle": "на месте",
    "patrol": "патрулирует",
    "rest": "отдыхает",
    "observe": "наблюдает",
    "travel": "в пути",
    "work": "торгует",
    "restock": "пополняет запас",
    "repair": "чинит сеть",
    "obtain_parts": "достаёт детали",
    "request_parts": "просит детали",
    "carry_parts": "несёт детали",
    "deliver_parts": "сдаёт детали",
}

TALK_LABELS = {
    "ivar": "Поговорить с Иваром",
    "marek": "Поговорить с Мареком",
    "eyra": "Поговорить с Эйрой",
}


def build_locations() -> dict[str, Location]:
    locations: dict[str, Location] = {}
    for location_id in LOCATION_ORDER:
        name, description, goes, move_label = _RAW_LOCATIONS[location_id]
        connections = tuple(other for other in LOCATION_ORDER if other != location_id)
        locations[location_id] = Location(
            id=location_id,
            name=name,
            description=description,
            goes=goes,
            move_label=move_label,
            connections=connections,
        )
    return locations


class Node17Content:
    """Settlement data for Узел-17. The engine asks this object; it does not embed the setting."""

    default_seed = 17041

    def __init__(self) -> None:
        self._locations = build_locations()
        self._behaviors: dict[str, Behavior] = {
            "ivar": IvarBehavior(),
            "marek": MarekBehavior(),
            "eyra": EyraBehavior(),
        }
        self._dialogue = build_dialogue_bundle()

    def locations(self) -> dict[str, Location]:
        return self._locations

    def behaviors(self) -> dict[str, Behavior]:
        return self._behaviors

    def settlement_name(self) -> str:
        return "Узел-17"

    def settlement_summary(self) -> str:
        return "Промышленный район. Около 800 жителей, по именам разобраны трое."

    def display_npc_ids(self) -> list[str]:
        return ["ivar", "marek", "eyra"]

    def talk_label(self, npc_id: str) -> str:
        return TALK_LABELS.get(npc_id, "Поговорить")

    def talk_log(self, npc_id: str) -> str:
        return {
            "ivar": "Разговор с Иваром.",
            "marek": "Разговор с Мареком.",
            "eyra": "Разговор с Эйрой.",
        }.get(npc_id, "Разговор.")

    def action_label(self, action_id: str) -> str:
        return ACTION_LABELS.get(action_id, action_id)

    def location_name(self, location_id: str) -> str:
        return self._locations[location_id].name

    def fatigue_band(self, fatigue: int) -> str:
        if fatigue >= 70:
            return "high"
        if fatigue >= 35:
            return "mid"
        return "low"

    def fatigue_label(self, fatigue: int) -> str:
        band = self.fatigue_band(fatigue)
        if fatigue >= 85:
            return "на пределе сил"
        if band == "high":
            return "усталость высокая"
        if band == "mid":
            return "усталость заметная"
        return "усталость низкая"

    def player_status(self, fatigue: int) -> str:
        if fatigue >= 80:
            return "Вы едва держитесь на ногах"
        if fatigue >= 60:
            return "Вы устали"
        if fatigue >= 30:
            return "Вы немного устали"
        return "Вы бодры"

    def threat_label(self, value: int) -> str:
        if value >= 45:
            return "тревога"
        if value >= 20:
            return "напряжённо"
        return "спокойно"

    def grid_label(self, value: int) -> str:
        if value >= 80:
            return "сеть стабильна"
        if value >= 50:
            return "сети нужно обслуживание"
        return "сеть на пределе"

    def stock_label(self, value: int) -> str:
        if value >= 60:
            return "запаса много"
        if value >= 30:
            return "запас обычный"
        return "запас на исходе"

    def dialogue_bundle(self) -> dict:
        return self._dialogue

    def build_initial(self, seed: int) -> WorldState:
        characters = {
            "player": Character(
                id="player",
                name="Саша Ковалёв",
                role="житель",
                is_player=True,
                location_id="market",
                fatigue=18,
                goals=[ordinary_day_goal()],
                current_action="idle",
                action_target=None,
                traits=["местный"],
                schedule={},
            ),
            "ivar": Character(
                id="ivar",
                name="Ивар",
                role="охранник",
                is_player=False,
                location_id="city_gates",
                fatigue=22,
                goals=[security_goal()],
                current_action="patrol",
                action_target=None,
                traits=["осторожный", "ответственный", "недоверчивый"],
                schedule={
                    "post": "city_gates",
                    "on_duty_start": 6,
                    "on_duty_end": 18,
                    "threat_alert": 50,
                    "patrol_relief": 2,
                },
            ),
            "marek": Character(
                id="marek",
                name="Марек",
                role="торговец",
                is_player=False,
                location_id="market",
                fatigue=16,
                goals=[profit_goal()],
                current_action="work",
                action_target=None,
                traits=["прагматичный", "общительный", "жадный"],
                schedule={
                    "post": "market",
                    "open_start": 8,
                    "open_end": 18,
                    "restock_below": 55,
                    "restock_amount": 12,
                    "work_min_stock": 12,
                    "work_consume": 3,
                },
            ),
            "eyra": Character(
                id="eyra",
                name="Эйра",
                role="инженер",
                is_player=False,
                location_id="workshop",
                fatigue=20,
                goals=[grid_goal()],
                current_action="repair",
                action_target=None,
                traits=["независимая", "упрямая", "любопытная"],
                schedule={
                    "post": "workshop",
                    "market": "market",
                    "repair_below": 85,
                    "repair_gain": 12,
                    "parts_cost": 8,
                    "parts_gain": 4,
                },
            ),
        }
        return WorldState(
            game_time=GAME_START,
            seed=seed,
            rng_counter=0,
            threat_level=8,
            grid_condition=64,
            market_stock=42,
            workshop_parts=6,
            tick_count=0,
            last_real_time=None,
            characters=characters,
        )

    def normalize_goals(self, state: WorldState) -> bool:
        """Replace a v0.0.1 goal string with that character's long-term goal."""
        changed = False
        for character in state.characters.values():
            upgraded = []
            for goal in character.goals:
                if goal.condition == UNRESOLVED_LEGACY or goal.id == "legacy":
                    upgraded.append(legacy_long_term(character.id, goal.label))
                    changed = True
                else:
                    upgraded.append(goal)
            character.goals = upgraded
        return changed

    def sync_goals(self, state: WorldState) -> None:
        """Give Eyra one active obtain-parts goal when the workshop cannot repair.

        The goal is created when the grid needs work and workshop parts are 0,
        and also while she is carrying a bundle that has not been delivered.
        It is not removed when the grid recovers. The engine completes it only
        when workshop_parts reaches the goal threshold, so it does not flicker.
        """
        eyra = state.characters.get("eyra")
        if eyra is None:
            return
        repair_below = int(eyra.schedule.get("repair_below", 85))
        cause = state.grid_condition < repair_below and state.workshop_parts <= 0
        carrying = eyra.carried_parts > 0 and state.workshop_parts <= 0
        if cause or carrying:
            ensure_active_goal(eyra, obtain_parts_goal())

    def after_tick(self, state: WorldState, rng: CounterRNG) -> None:
        state.tick_count += 1
        if state.tick_count % 6 == 0:
            state.grid_condition = max(0, min(100, state.grid_condition - 2))
        if state.tick_count % 8 == 0:
            state.market_stock = max(0, min(100, state.market_stock - 1))
        drift = rng.choice((-1, 0, 0, 0, 1))
        state.threat_level = max(0, min(100, state.threat_level + drift))
