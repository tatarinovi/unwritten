from __future__ import annotations

import json
from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.schema import (
    Base,
    CharacterRow,
    DialogueMessageRow,
    EventRow,
    NpcMemoryRow,
    ProcessedActionRow,
    WorldMetaRow,
)
from app.db.session import make_engine, make_session_factory
from app.engine.goals import dump_goals, parse_stored_goals
from app.engine.models import Character, GameEvent, WorldState
from app.engine.timekeep import (
    GAME_START,
    dump_real,
    format_iso,
    load_real,
    parse_game_time,
    shift_from_old_epoch,
    uses_old_epoch,
)


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
        self._ensure_save_columns(session)
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
                calendar_epoch=GAME_START.year,
            )
        )
        for character in state.characters.values():
            session.add(self._character_row(character))

    def load(self, session: Session) -> WorldState:
        self._ensure_save_columns(session)
        self._migrate_epoch(session)
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
            row.goal = dump_goals(character.goals)
            row.carried_parts = character.carried_parts
            row.parts_result = character.parts_result
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

    def list_events_by_kinds(self, session: Session, kinds: tuple[str, ...], limit: int) -> list[EventRow]:
        """Recent events of the given kinds, oldest first. No schema change."""
        if not kinds or limit <= 0:
            return []
        rows = session.scalars(
            select(EventRow).where(EventRow.kind.in_(kinds)).order_by(EventRow.id.desc()).limit(limit)
        ).all()
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

    def list_dialogue(self, session: Session, npc_id: str, limit: int) -> list[DialogueMessageRow]:
        rows = session.scalars(
            select(DialogueMessageRow)
            .where(DialogueMessageRow.npc_id == npc_id)
            .order_by(DialogueMessageRow.id.desc())
            .limit(limit)
        ).all()
        return list(reversed(rows))

    def add_dialogue(
        self,
        session: Session,
        *,
        npc_id: str,
        role: str,
        body: str,
        game_time: str,
        source: str,
        request_id: str,
    ) -> None:
        session.add(
            DialogueMessageRow(
                npc_id=npc_id,
                role=role,
                body=body,
                game_time=game_time,
                source=source,
                request_id=request_id,
            )
        )

    def list_memory(self, session: Session, npc_id: str, limit: int) -> list[NpcMemoryRow]:
        rows = session.scalars(
            select(NpcMemoryRow)
            .where(NpcMemoryRow.npc_id == npc_id)
            .order_by(NpcMemoryRow.id.desc())
            .limit(limit)
        ).all()
        return list(reversed(rows))

    def add_memory(
        self,
        session: Session,
        *,
        npc_id: str,
        body: str,
        kind: str,
        source: str,
        game_time: str,
        confirmed: bool,
        request_id: str,
    ) -> None:
        session.add(
            NpcMemoryRow(
                npc_id=npc_id,
                body=body,
                kind=kind,
                source=source,
                game_time=game_time,
                confirmed=confirmed,
                request_id=request_id,
            )
        )

    def _character_row(self, character: Character) -> CharacterRow:
        return CharacterRow(
            id=character.id,
            name=character.name,
            role=character.role,
            is_player=character.is_player,
            location_id=character.location_id,
            fatigue=character.fatigue,
            goal=dump_goals(character.goals),
            carried_parts=character.carried_parts,
            parts_result=character.parts_result,
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
            goals=parse_stored_goals(row.goal),
            carried_parts=int(row.carried_parts or 0),
            parts_result=str(row.parts_result or ""),
            current_action=row.current_action,
            action_target=row.action_target,
            traits=list(json.loads(row.traits_json)),
            schedule=dict(json.loads(row.schedule_json)),
        )

    def _table_exists(self, session: Session, table: str) -> bool:
        row = session.execute(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table},
        ).first()
        return row is not None

    def _column_names(self, session: Session, table: str) -> set[str]:
        if not self._table_exists(session, table):
            return set()
        rows = session.execute(text(f"PRAGMA table_info({table})")).all()
        return {str(row[1]) for row in rows}

    def _ensure_save_columns(self, session: Session) -> None:
        """Add columns that v0.0.1 saves do not have. Existing rows stay."""
        if self._table_exists(session, "characters") and "carried_parts" not in self._column_names(session, "characters"):
            session.execute(
                text("ALTER TABLE characters ADD COLUMN carried_parts INTEGER NOT NULL DEFAULT 0")
            )
        if self._table_exists(session, "characters") and "parts_result" not in self._column_names(session, "characters"):
            session.execute(
                text("ALTER TABLE characters ADD COLUMN parts_result VARCHAR(16) NOT NULL DEFAULT ''")
            )
        if self._table_exists(session, "world_meta") and "calendar_epoch" not in self._column_names(session, "world_meta"):
            session.execute(text("ALTER TABLE world_meta ADD COLUMN calendar_epoch INTEGER"))

    def _migrate_epoch(self, session: Session) -> None:
        """Shift a 2061-epoch save onto 12 April 2036, once.

        Elapsed game duration is preserved with datetime subtraction, so 10:30
        stays 10:30. Real-world last_real_time is not touched. A row already
        marked 2036 is left alone, including a second load of the same file.
        """
        meta = session.get(WorldMetaRow, 1)
        if meta is None or meta.calendar_epoch == GAME_START.year:
            return
        moment = parse_game_time(meta.game_time)
        if uses_old_epoch(moment):
            meta.game_time = format_iso(shift_from_old_epoch(moment))
            events = session.scalars(select(EventRow)).all()
            for event in events:
                event.game_time = format_iso(shift_from_old_epoch(parse_game_time(event.game_time)))
        meta.calendar_epoch = GAME_START.year
