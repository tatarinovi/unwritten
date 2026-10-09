from __future__ import annotations

import json
from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.schema import Base, CharacterRow, EventRow, ProcessedActionRow, WorldMetaRow
from app.db.session import make_engine, make_session_factory
from app.engine.models import Character, GameEvent, WorldState
from app.engine.timekeep import dump_real, format_iso, load_real, parse_game_time


class Repository:
    def __init__(self, database_url: str) -> None:
        self.engine = make_engine(database_url)
        self.sessions = make_session_factory(self.engine)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        session = self.sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def has_world(self, session: Session) -> bool:
        return session.get(WorldMetaRow, 1) is not None

    def insert_world(self, session: Session, state: WorldState) -> None:
        session.add(
            WorldMetaRow(
                id=1,
                game_time=format_iso(state.game_time),
                seed=state.seed,
                rng_counter=state.rng_counter,
                threat_level=state.threat_level,
                grid_condition=state.grid_condition,
                market_stock=state.market_stock,
                workshop_parts=state.workshop_parts,
                tick_count=state.tick_count,
                last_real_time=dump_real(state.last_real_time),
            )
        )
        for character in state.characters.values():
            session.add(self._character_row(character))

    def load(self, session: Session) -> WorldState:
        meta = session.get(WorldMetaRow, 1)
        if meta is None:
            raise RuntimeError("world is not initialized")
        rows = session.scalars(select(CharacterRow)).all()
        characters = {row.id: self._character(row) for row in rows}
        return WorldState(
            game_time=parse_game_time(meta.game_time),
            seed=meta.seed,
            rng_counter=meta.rng_counter,
            threat_level=meta.threat_level,
            grid_condition=meta.grid_condition,
            market_stock=meta.market_stock,
            workshop_parts=meta.workshop_parts,
            tick_count=meta.tick_count,
            last_real_time=load_real(meta.last_real_time),
            characters=characters,
        )

    def save_state(self, session: Session, state: WorldState) -> None:
        meta = session.get(WorldMetaRow, 1)
        if meta is None:
            raise RuntimeError("world is not initialized")
        meta.game_time = format_iso(state.game_time)
        meta.seed = state.seed
        meta.rng_counter = state.rng_counter
        meta.threat_level = state.threat_level
        meta.grid_condition = state.grid_condition
        meta.market_stock = state.market_stock
        meta.workshop_parts = state.workshop_parts
        meta.tick_count = state.tick_count
        meta.last_real_time = dump_real(state.last_real_time)
        for character in state.characters.values():
            row = session.get(CharacterRow, character.id)
            if row is None:
                raise RuntimeError(f"missing character {character.id}")
            row.name = character.name
            row.role = character.role
            row.is_player = character.is_player
            row.location_id = character.location_id
            row.fatigue = character.fatigue
            row.goal = character.goal
            row.current_action = character.current_action
            row.action_target = character.action_target
            row.traits_json = json.dumps(character.traits, ensure_ascii=False)
            row.schedule_json = json.dumps(character.schedule, ensure_ascii=False)

    def add_event(self, session: Session, event: GameEvent) -> None:
        session.add(
            EventRow(
                game_time=format_iso(event.game_time),
                kind=event.kind,
                message=event.message,
                actor_id=event.actor_id,
                data_json=json.dumps(event.data, ensure_ascii=False),
            )
        )

    def list_events(self, session: Session, limit: int) -> list[EventRow]:
        rows = session.scalars(select(EventRow).order_by(EventRow.id.desc()).limit(limit)).all()
        return list(reversed(rows))

    def count_events(self, session: Session) -> int:
        value = session.scalar(select(func.count()).select_from(EventRow))
        return int(value or 0)

    def get_processed(self, session: Session, action_id: str) -> str | None:
        row = session.get(ProcessedActionRow, action_id)
        if row is None:
            return None
        return row.response_json

    def save_processed(self, session: Session, action_id: str, response_json: str) -> None:
        session.add(ProcessedActionRow(action_id=action_id, response_json=response_json))

    def _character_row(self, character: Character) -> CharacterRow:
        return CharacterRow(
            id=character.id,
            name=character.name,
            role=character.role,
            is_player=character.is_player,
            location_id=character.location_id,
            fatigue=character.fatigue,
            goal=character.goal,
            current_action=character.current_action,
            action_target=character.action_target,
            traits_json=json.dumps(character.traits, ensure_ascii=False),
            schedule_json=json.dumps(character.schedule, ensure_ascii=False),
        )

    def _character(self, row: CharacterRow) -> Character:
        return Character(
            id=row.id,
            name=row.name,
            role=row.role,
            is_player=bool(row.is_player),
            location_id=row.location_id,
            fatigue=row.fatigue,
            goal=row.goal,
            current_action=row.current_action,
            action_target=row.action_target,
            traits=list(json.loads(row.traits_json)),
            schedule=dict(json.loads(row.schedule_json)),
        )
