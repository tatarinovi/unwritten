from __future__ import annotations

import sqlite3
from pathlib import Path

from app.engine.timekeep import GAME_START, OLD_GAME_START, shift_from_old_epoch
from app.main import build_world


def test_epoch_shift_keeps_clock_time() -> None:
    assert shift_from_old_epoch(OLD_GAME_START) == GAME_START
    ten_thirty = OLD_GAME_START.replace(hour=10, minute=30)
    shifted = shift_from_old_epoch(ten_thirty)
    assert shifted.year == 2036
    assert shifted.month == 4
    assert shifted.day == 12
    assert (shifted.hour, shifted.minute) == (10, 30)
    next_morning = OLD_GAME_START.replace(day=13)
    shifted_next = shift_from_old_epoch(next_morning)
    assert (shifted_next.year, shifted_next.month, shifted_next.day) == (2036, 4, 13)
    assert (shifted_next.hour, shifted_next.minute) == (8, 0)


def _insert_old_save(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE world_meta (
                id INTEGER PRIMARY KEY,
                game_time VARCHAR(32) NOT NULL,
                seed INTEGER NOT NULL,
                rng_counter INTEGER NOT NULL,
                threat_level INTEGER NOT NULL,
                grid_condition INTEGER NOT NULL,
                market_stock INTEGER NOT NULL,
                workshop_parts INTEGER NOT NULL,
                tick_count INTEGER NOT NULL,
                last_real_time VARCHAR(40)
            );
            CREATE TABLE characters (
                id VARCHAR(32) PRIMARY KEY,
                name VARCHAR(80) NOT NULL,
                role VARCHAR(80) NOT NULL,
                is_player BOOLEAN NOT NULL,
                location_id VARCHAR(32) NOT NULL,
                fatigue INTEGER NOT NULL,
                goal VARCHAR(160) NOT NULL,
                current_action VARCHAR(32) NOT NULL,
                action_target VARCHAR(32),
                traits_json TEXT NOT NULL,
                schedule_json TEXT NOT NULL
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_time VARCHAR(32) NOT NULL,
                kind VARCHAR(40) NOT NULL,
                message TEXT NOT NULL,
                actor_id VARCHAR(32),
                data_json TEXT NOT NULL
            );
            CREATE TABLE processed_actions (
                action_id VARCHAR(80) PRIMARY KEY,
                response_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO world_meta (
                id, game_time, seed, rng_counter, threat_level, grid_condition,
                market_stock, workshop_parts, tick_count, last_real_time
            ) VALUES (1, ?, 17041, 0, 8, 64, 42, 6, 4, ?)
            """,
            ("2061-04-12T10:30:00", "2026-06-01T15:04:05+00:00"),
        )
        people = [
            ("player", "Саша Ковалёв", "житель", 1, "market", "Прожить обычный день", "idle"),
            ("ivar", "Ивар", "охранник", 0, "city_gates", "Безопасность поселения", "patrol"),
            ("marek", "Марек", "торговец", 0, "market", "Прибыль", "work"),
            ("eyra", "Эйра", "инженер", 0, "workshop", "Держать энергосеть", "repair"),
        ]
        connection.executemany(
            """
            INSERT INTO characters (
                id, name, role, is_player, location_id, fatigue, goal,
                current_action, action_target, traits_json, schedule_json
            ) VALUES (?, ?, ?, ?, ?, 10, ?, ?, NULL, '[]', '{}')
            """,
            people,
        )
        connection.execute(
            """
            INSERT INTO events (game_time, kind, message, actor_id, data_json)
            VALUES ('2061-04-12T09:15:00', 'world_start', 'старое утро', NULL, '{}')
            """,
        )
        connection.commit()
    finally:
        connection.close()


def _clocks(path: Path) -> tuple[str, str, str | None, int | None]:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT game_time, last_real_time, calendar_epoch FROM world_meta WHERE id = 1"
        ).fetchone()
        assert row is not None
        game_time, last_real, epoch = row
        event_row = connection.execute("SELECT game_time FROM events").fetchone()
        assert event_row is not None
        event_time = event_row[0]
        return game_time, event_time, last_real, epoch
    finally:
        connection.close()


def test_old_2061_save_shifts_once_and_keeps_last_visit(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    _insert_old_save(path)
    url = "sqlite:///" + path.resolve().as_posix()

    engine = build_world(url)
    try:
        snap = engine.snapshot()
        assert snap["time"] == "2036-04-12T10:30:00"
        assert snap["day_label"] == "12 апреля 2036, 10:30"
        events = engine.list_events()
        assert events[0]["time"] == "2036-04-12T09:15:00"
        marek = next(npc for npc in engine.list_npcs() if npc["id"] == "marek")
        assert marek["goal"] == "Прибыль"
        profit = marek["goals"][0]
        assert profit["id"] == "profit"
        assert profit["kind"] == "long_term"
        assert profit["status"] == "active"
        assert marek["carried_parts"] == 0
    finally:
        engine.close()

    game_time, event_time, last_real, epoch = _clocks(path)
    assert game_time == "2036-04-12T10:30:00"
    assert event_time == "2036-04-12T09:15:00"
    assert last_real == "2026-06-01T15:04:05+00:00"
    assert epoch == 2036

    again = build_world(url)
    try:
        assert again.snapshot()["time"] == "2036-04-12T10:30:00"
        assert again.list_events()[0]["time"] == "2036-04-12T09:15:00"
    finally:
        again.close()

    game_time, event_time, last_real, epoch = _clocks(path)
    assert game_time == "2036-04-12T10:30:00"
    assert event_time == "2036-04-12T09:15:00"
    assert last_real == "2026-06-01T15:04:05+00:00"
    assert epoch == 2036
