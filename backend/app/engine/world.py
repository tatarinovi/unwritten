from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from app.db.repository import Repository
from app.db.schema import EventRow
from app.engine.dialogue import DialogueProvider
from app.engine.effects import clamp, make_event
from app.engine.errors import ActionError
from app.engine.models import Character, WorldState
from app.engine.npc import run_npc_tick
from app.engine.rng import CounterRNG
from app.engine.timekeep import (
    MAX_ABSENCE_MINUTES,
    MOVE_MINUTES,
    TALK_MINUTES,
    add_minutes,
    duration_phrase,
    ensure_utc,
    format_clock,
    format_day_label,
    format_iso,
    minutes_between,
    parse_game_time,
    tick_marks,
)


class WorldEngine:
    """Game time, movement, NPC ticks, and one-transaction saves.

    Setting text and utility scores live in the content object. This class
    asks a DialogueProvider for lines and does not know whether they are templates.
    """

    def __init__(self, repository: Repository, content: Any, dialogue: DialogueProvider) -> None:
        self.repo = repository
        self.content = content
        self.dialogue = dialogue
        self._lock = threading.RLock()

    def close(self) -> None:
        self.repo.dispose()

    def ensure_initialized(self, seed: int | None = None) -> None:
        with self._lock:
            with self.repo.transaction() as session:
                if self.repo.has_world(session):
                    return
                chosen = self.content.default_seed if seed is None else seed
                state = self.content.build_initial(chosen)
                self.repo.insert_world(session, state)
                self.repo.add_event(
                    session,
                    make_event(
                        state,
                        "world_start",
                        "Узел-17 просыпается. Обычное утро, 12 апреля 2061 года.",
                        None,
                    ),
                )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            with self.repo.transaction() as session:
                return self._snapshot(self.repo.load(session))

    def list_npcs(self) -> list[dict[str, Any]]:
        with self._lock:
            with self.repo.transaction() as session:
                state = self.repo.load(session)
                return [self._npc_dict(npc) for npc in self._ordered_npcs(state, present_only=False)]

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        bounded = max(1, min(limit, 5000))
        with self._lock:
            with self.repo.transaction() as session:
                rows = self.repo.list_events(session, bounded)
                return [self._event_dict(row) for row in rows]

    def event_count(self) -> int:
        with self._lock:
            with self.repo.transaction() as session:
                return self.repo.count_events(session)

    def update_for_test(
        self,
        *,
        character: dict[str, Any] | None = None,
        world_fields: dict[str, Any] | None = None,
    ) -> None:
        allowed_character = {"location_id", "fatigue", "current_action", "action_target", "goal"}
        allowed_world = {"threat_level", "grid_condition", "market_stock", "workshop_parts", "tick_count"}
        with self._lock:
            with self.repo.transaction() as session:
                state = self.repo.load(session)
                if world_fields:
                    for key, value in world_fields.items():
                        if key not in allowed_world:
                            raise ValueError(key)
                        setattr(state, key, int(value))
                if character:
                    npc = state.characters[str(character["id"])]
                    for key, value in character.items():
                        if key == "id":
                            continue
                        if key not in allowed_character:
                            raise ValueError(key)
                        setattr(npc, key, value)
                self.repo.save_state(session, state)

    def perform(
        self,
        action_type: str,
        params: dict[str, Any] | None = None,
        action_id: str = "",
        now: datetime | None = None,
        inject_failure: bool = False,
    ) -> dict[str, Any]:
        params = dict(params or {})
        action_id = action_id.strip()
        if not action_id:
            raise ActionError("Нужен идентификатор действия.")
        with self._lock:
            with self.repo.transaction() as session:
                replay = self._replay(session, action_id)
                if replay is not None:
                    return replay
                state = self.repo.load(session)
                detail, player_events, minutes = self._apply_player_action(state, action_type, params)
                self._slide_cursor(state, now)
                npc_events = self._advance(state, minutes)
                return self._persist(
                    session,
                    state,
                    action_id,
                    [*player_events, *npc_events],
                    {"detail": detail},
                    inject_failure,
                )

    def speak(
        self,
        npc_id: str,
        action_id: str,
        reply_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        action_id = action_id.strip()
        if not action_id:
            raise ActionError("Нужен идентификатор действия.")
        with self._lock:
            with self.repo.transaction() as session:
                replay = self._replay(session, action_id)
                if replay is not None:
                    return replay
                state = self.repo.load(session)
                npc = state.characters.get(npc_id)
                if npc is None or npc.is_player:
                    raise ActionError("Такого человека здесь нет.")
                if npc.location_id != state.player.location_id:
                    raise ActionError("Этого человека сейчас нет рядом.")
                turn = self.dialogue.generate(npc, state, reply_id)
                event = make_event(
                    state,
                    "dialogue",
                    self.content.talk_log(npc_id),
                    state.player.id,
                    {"npc_id": npc_id, "reply_id": reply_id},
                )
                state.player.fatigue = clamp(state.player.fatigue + 1)
                self._slide_cursor(state, now)
                npc_events = self._advance(state, TALK_MINUTES)
                still_here = state.characters[npc_id].location_id == state.player.location_id
                note = None if still_here else f"{npc.name} уже не рядом. Разговор окончен."
                options = turn.options if still_here else []
                return self._persist(
                    session,
                    state,
                    action_id,
                    [event, *npc_events],
                    {
                        "npc_id": turn.npc_id,
                        "npc_name": turn.npc_name,
                        "line": turn.line,
                        "options": options,
                        "note": note,
                    },
                    False,
                )

    def resume(self, now: datetime) -> dict[str, Any]:
        now = ensure_utc(now)
        with self._lock:
            with self.repo.transaction() as session:
                state = self.repo.load(session)
                if state.last_real_time is None:
                    state.last_real_time = now
                    self.repo.save_state(session, state)
                    snapshot = self._snapshot(state)
                    return self._resume_body(0, False, snapshot)
                if now <= state.last_real_time:
                    return self._resume_body(0, False, self._snapshot(state))
                delta = minutes_between(state.last_real_time, now)
                if delta <= 0:
                    return self._resume_body(0, False, self._snapshot(state))
                advance = min(delta, MAX_ABSENCE_MINUTES)
                capped = delta > MAX_ABSENCE_MINUTES
                if capped:
                    message = (
                        "Вас не было дольше суток. Мир сдвинулся только на 24 часа — "
                        "остальное время без вас не считается."
                    )
                else:
                    message = f"Вас не было {duration_phrase(advance)}."
                self.repo.add_event(session, make_event(state, "absence", message, None, {"minutes": advance}))
                for event in self._advance(state, advance):
                    self.repo.add_event(session, event)
                state.last_real_time = now
                self.repo.save_state(session, state)
                return self._resume_body(advance, capped, self._snapshot(state))

    def _resume_body(self, advanced: int, capped: bool, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "advanced_minutes": advanced,
            "capped": capped,
            "game_time": snapshot["time"],
            "world": snapshot,
        }

    def _replay(self, session: Any, action_id: str) -> dict[str, Any] | None:
        stored = self.repo.get_processed(session, action_id)
        if stored is None:
            return None
        payload = json.loads(stored)
        payload["replayed"] = True
        return payload

    def _persist(
        self,
        session: Any,
        state: WorldState,
        action_id: str,
        events: list[Any],
        body: dict[str, Any],
        inject_failure: bool,
    ) -> dict[str, Any]:
        self.repo.save_state(session, state)
        for event in events:
            self.repo.add_event(session, event)
        session.flush()
        if inject_failure:
            raise RuntimeError("injected failure")
        payload = {**body, "replayed": False, "world": self._snapshot(state)}
        self.repo.save_processed(session, action_id, json.dumps(payload, ensure_ascii=False))
        return payload

    def _apply_player_action(
        self,
        state: WorldState,
        action_type: str,
        params: dict[str, Any],
    ) -> tuple[str, list[Any], int]:
        player = state.player
        locations = self.content.locations()
        if action_type == "look":
            event = make_event(
                state,
                "player_look",
                "Вы осматриваетесь.",
                player.id,
                {"location_id": player.location_id},
            )
            return "Вы осматриваетесь.", [event], 0
        if action_type == "wait":
            minutes = params.get("minutes")
            if minutes not in (10, 30, 60):
                raise ActionError("Так ждать нельзя. Выберите 10, 30 или 60 минут.")
            if minutes == 60:
                detail = "Вы ждёте 1 час."
            elif minutes == 30:
                detail = "Вы ждёте 30 минут."
            else:
                detail = "Вы ждёте 10 минут."
            player.fatigue = clamp(player.fatigue - (minutes // 10))
            event = make_event(state, "player_wait", detail, player.id, {"minutes": minutes})
            return detail, [event], int(minutes)
        if action_type == "move":
            dest_id = params.get("location_id")
            if not isinstance(dest_id, str) or dest_id not in locations:
                raise ActionError("Такого места нет.")
            if dest_id == player.location_id:
                raise ActionError("Вы уже здесь.")
            current = locations[player.location_id]
            if dest_id not in current.connections:
                raise ActionError("Отсюда туда не пройти.")
            dest = locations[dest_id]
            origin = player.location_id
            detail = f"Вы идёте {dest.goes}."
            event = make_event(state, "player_move", detail, player.id, {"from": origin, "to": dest_id})
            player.location_id = dest_id
            player.fatigue = clamp(player.fatigue + 3)
            player.current_action = "travel"
            return detail, [event], MOVE_MINUTES
        raise ActionError("Неизвестное действие.")

    def _advance(self, state: WorldState, minutes: int) -> list[Any]:
        if minutes <= 0:
            return []
        start = state.game_time
        rng = CounterRNG(state.seed, state.rng_counter)
        events: list[Any] = []
        behaviors = self.content.behaviors()
        locations = self.content.locations()
        for mark in tick_marks(start, minutes):
            state.game_time = mark
            events.extend(run_npc_tick(state, behaviors, locations, rng))
            self.content.after_tick(state, rng)
        state.game_time = add_minutes(start, minutes)
        state.rng_counter = rng.counter
        return events

    def _slide_cursor(self, state: WorldState, now: datetime | None) -> None:
        if now is None:
            return
        current = ensure_utc(now)
        if state.last_real_time is None or current > state.last_real_time:
            state.last_real_time = current

    def _snapshot(self, state: WorldState) -> dict[str, Any]:
        locations = self.content.locations()
        place = locations[state.player.location_id]
        return {
            "time": format_iso(state.game_time),
            "day_label": format_day_label(state.game_time),
            "seed": state.seed,
            "location": {
                "id": place.id,
                "name": place.name,
                "description": place.description,
            },
            "present_npcs": [self._npc_dict(npc) for npc in self._ordered_npcs(state, present_only=True)],
            "npcs": [self._npc_dict(npc) for npc in self._ordered_npcs(state, present_only=False)],
            "player": {
                "id": state.player.id,
                "name": state.player.name,
                "role": state.player.role,
                "fatigue": state.player.fatigue,
                "status_label": self.content.player_status(state.player.fatigue),
                "location_id": state.player.location_id,
                "goal": state.player.goal,
            },
            "settlement": {
                "name": self.content.settlement_name(),
                "summary": self.content.settlement_summary(),
                "threat_level": state.threat_level,
                "threat_label": self.content.threat_label(state.threat_level),
                "grid_condition": state.grid_condition,
                "grid_label": self.content.grid_label(state.grid_condition),
                "market_stock": state.market_stock,
                "stock_label": self.content.stock_label(state.market_stock),
                "workshop_parts": state.workshop_parts,
            },
            "available_actions": self._actions(state),
        }

    def _actions(self, state: WorldState) -> list[dict[str, Any]]:
        locations = self.content.locations()
        current = locations[state.player.location_id]
        actions: list[dict[str, Any]] = []
        for dest_id in current.connections:
            dest = locations[dest_id]
            actions.append(
                {
                    "type": "move",
                    "label": dest.move_label,
                    "params": {"location_id": dest_id},
                }
            )
        actions.append({"type": "look", "label": "Осмотреться", "params": {}})
        for npc in self._ordered_npcs(state, present_only=True):
            actions.append(
                {
                    "type": "talk",
                    "label": self.content.talk_label(npc.id),
                    "params": {"npc_id": npc.id},
                }
            )
        actions.append({"type": "wait", "label": "Подождать 10 минут", "params": {"minutes": 10}})
        actions.append({"type": "wait", "label": "Подождать 30 минут", "params": {"minutes": 30}})
        actions.append({"type": "wait", "label": "Подождать час", "params": {"minutes": 60}})
        return actions

    def _ordered_npcs(self, state: WorldState, *, present_only: bool) -> list[Character]:
        by_id = {character.id: character for character in state.characters.values() if not character.is_player}
        ordered: list[Character] = []
        for npc_id in self.content.display_npc_ids():
            npc = by_id.get(npc_id)
            if npc is None:
                continue
            if present_only and npc.location_id != state.player.location_id:
                continue
            ordered.append(npc)
        return ordered

    def _npc_dict(self, npc: Character) -> dict[str, Any]:
        place = self.content.locations()[npc.location_id]
        return {
            "id": npc.id,
            "name": npc.name,
            "role": npc.role,
            "location_id": npc.location_id,
            "location_name": place.name,
            "fatigue": npc.fatigue,
            "fatigue_label": self.content.fatigue_label(npc.fatigue),
            "goal": npc.goal,
            "current_action": npc.current_action,
            "action_label": self.content.action_label(npc.current_action),
            "traits": list(npc.traits),
        }

    def _event_dict(self, row: EventRow) -> dict[str, Any]:
        moment = parse_game_time(row.game_time)
        return {
            "id": row.id,
            "time": format_iso(moment),
            "clock": format_clock(moment),
            "kind": row.kind,
            "message": row.message,
            "actor_id": row.actor_id,
            "data": json.loads(row.data_json),
        }
