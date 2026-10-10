from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WorldMetaRow(Base):
    __tablename__ = "world_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_time: Mapped[str] = mapped_column(String(32), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    rng_counter: Mapped[int] = mapped_column(Integer, nullable=False)
    threat_level: Mapped[int] = mapped_column(Integer, nullable=False)
    grid_condition: Mapped[int] = mapped_column(Integer, nullable=False)
    market_stock: Mapped[int] = mapped_column(Integer, nullable=False)
    workshop_parts: Mapped[int] = mapped_column(Integer, nullable=False)
    tick_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_real_time: Mapped[str | None] = mapped_column(String(40), nullable=True)
    calendar_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=2036)


class CharacterRow(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    is_player: Mapped[bool] = mapped_column(Boolean, nullable=False)
    location_id: Mapped[str] = mapped_column(String(32), nullable=False)
    fatigue: Mapped[int] = mapped_column(Integer, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    carried_parts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parts_result: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    current_action: Mapped[str] = mapped_column(String(32), nullable=False)
    action_target: Mapped[str | None] = mapped_column(String(32), nullable=True)
    traits_json: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_json: Mapped[str] = mapped_column(Text, nullable=False)


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_time: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)


class ProcessedActionRow(Base):
    __tablename__ = "processed_actions"

    action_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)


class DialogueMessageRow(Base):
    __tablename__ = "dialogue_messages"
    __table_args__ = (UniqueConstraint("request_id", "role", name="uq_dialogue_request_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False)
    npc_id: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    game_time: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)


class NpcMemoryRow(Base):
    """One NPC's memory. Rows are never copied to another character.

    A later social memory would be an explicit write for one npc_id, with its
    own source. It is not a merge of these rows and it does not exist yet.
    """

    __tablename__ = "npc_memory"
    __table_args__ = (UniqueConstraint("request_id", "kind", name="uq_memory_request_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False)
    npc_id: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    game_time: Mapped[str] = mapped_column(String(32), nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
