from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.engine.errors import ActionError
from tests.conftest import open_world


def signature(engine) -> dict:
    snap = engine.snapshot()
    events = []
    for event in engine.list_events(limit=5000):
        data = tuple(sorted(event["data"].items()))
        events.append((event["time"], event["kind"], event["actor_id"], event["message"], data))
    npcs = [
        (npc["id"], npc["location_id"], npc["fatigue"], npc["current_action"])
        for npc in engine.list_npcs()
    ]
    settlement = snap["settlement"]
    return {
        "time": snap["time"],
        "location": snap["location"]["id"],
        "player_fatigue": snap["player"]["fatigue"],
        "threat": settlement["threat_level"],
        "grid": settlement["grid_condition"],
        "stock": settlement["market_stock"],
        "parts": settlement["workshop_parts"],
        "npcs": npcs,
        "events": events,
    }


def npc_by_id(engine, npc_id: str) -> dict:
    return next(npc for npc in engine.list_npcs() if npc["id"] == npc_id)


def test_01_first_launch_creates_world_and_three_npcs(world) -> None:
    snap = world.snapshot()
    assert snap["time"] == "2036-04-12T08:00:00"
    assert snap["day_label"] == "12 апреля 2036, 08:00"
    assert snap["location"]["id"] == "market"
    npcs = world.list_npcs()
    assert [npc["id"] for npc in npcs] == ["ivar", "marek", "eyra"]
    assert [npc["name"] for npc in npcs] == ["Ивар", "Марек", "Эйра"]
    assert npc_by_id(world, "ivar")["goal"] == "Безопасность поселения"
    assert npc_by_id(world, "marek")["goal"] == "Прибыль"
    assert npc_by_id(world, "eyra")["goal"] == "Держать энергосеть"
    assert npc_by_id(world, "eyra")["carried_parts"] == 0
    assert len({npc["id"] for npc in npcs}) == 3
    before = world.event_count()
    world.ensure_initialized()
    world.ensure_initialized(seed=1)
    assert world.event_count() == before
    assert [npc["id"] for npc in world.list_npcs()] == ["ivar", "marek", "eyra"]


def test_02_player_movement_changes_location(world) -> None:
    result = world.perform("move", {"location_id": "workshop"}, "move-1")
    assert result["replayed"] is False
    assert result["world"]["location"]["id"] == "workshop"
    assert world.snapshot()["location"]["id"] == "workshop"
    assert any(event["kind"] == "player_move" for event in world.list_events())


def test_03_action_advances_game_time(world) -> None:
    world.perform("wait", {"minutes": 60}, "wait-1")
    assert world.snapshot()["time"] == "2036-04-12T09:00:00"


def test_04_npcs_act_when_time_advances(world) -> None:
    world.perform("wait", {"minutes": 60}, "wait-npcs")
    kinds = {(event["actor_id"], event["kind"]) for event in world.list_events()}
    assert ("ivar", "npc_patrol") in kinds
    assert ("marek", "npc_restock") in kinds
    assert ("eyra", "npc_repair") in kinds
    assert [npc["id"] for npc in world.list_npcs()] == ["ivar", "marek", "eyra"]


def test_05_high_fatigue_chooses_rest(world) -> None:
    world.update_for_test(character={"id": "ivar", "fatigue": 96, "location_id": "city_gates", "current_action": "patrol"})
    world.perform("wait", {"minutes": 10}, "fatigue-rest")
    ivar = npc_by_id(world, "ivar")
    assert ivar["current_action"] == "rest"
    assert ivar["location_id"] == "city_gates"
    assert ivar["fatigue"] < 96
    ivar_events = [event for event in world.list_events() if event["actor_id"] == "ivar"]
    assert any(event["kind"] == "npc_rest" for event in ivar_events)
    assert not any(event["kind"] == "npc_patrol" for event in ivar_events)


def test_05b_repair_need_sends_eyra_to_workshop(world) -> None:
    world.update_for_test(
        character={"id": "eyra", "location_id": "market", "fatigue": 12, "current_action": "observe"},
        world_fields={"grid_condition": 40, "workshop_parts": 4},
    )
    world.perform("wait", {"minutes": 10}, "eyra-repair")
    eyra = npc_by_id(world, "eyra")
    assert eyra["location_id"] == "workshop"
    moves = [
        event
        for event in world.list_events()
        if event["kind"] == "npc_move" and event["actor_id"] == "eyra"
    ]
    assert len(moves) == 1
    assert moves[0]["data"]["from"] == "market"
    assert moves[0]["data"]["to"] == "workshop"


def test_05c_eyra_seeks_parts_when_workshop_is_empty(world) -> None:
    world.update_for_test(
        character={"id": "eyra", "location_id": "workshop", "fatigue": 10, "current_action": "observe"},
        world_fields={"grid_condition": 30, "workshop_parts": 0, "market_stock": 40},
    )
    world.perform("wait", {"minutes": 10}, "eyra-parts")
    eyra = npc_by_id(world, "eyra")
    assert eyra["location_id"] == "market"
    moves = [
        event
        for event in world.list_events()
        if event["kind"] == "npc_move" and event["actor_id"] == "eyra"
    ]
    assert moves[-1]["data"]["to"] == "market"
    assert moves[-1]["data"]["reason"] == "parts"


def test_06_state_persists_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "save.db"
    engine = open_world(path)
    engine.perform("move", {"location_id": "workshop"}, "persist-move")
    expected_time = engine.snapshot()["time"]
    expected_fatigue = engine.snapshot()["player"]["fatigue"]
    engine.close()

    restored = open_world(path)
    try:
        snap = restored.snapshot()
        assert snap["location"]["id"] == "workshop"
        assert snap["time"] == expected_time
        assert snap["player"]["fatigue"] == expected_fatigue
        assert snap["time"] == "2036-04-12T08:10:00"
        restored.perform("wait", {"minutes": 10}, "after-restart")
        assert restored.snapshot()["time"] == "2036-04-12T08:20:00"
        assert restored.snapshot()["location"]["id"] == "workshop"
    finally:
        restored.close()


def test_07_catchup_is_idempotent_for_the_same_window(world) -> None:
    start = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    anchored = world.resume(start)
    assert anchored["advanced_minutes"] == 0
    assert world.snapshot()["time"] == "2036-04-12T08:00:00"

    caught_up = world.resume(start + timedelta(hours=3))
    assert caught_up["advanced_minutes"] == 180
    assert caught_up["capped"] is False
    assert world.snapshot()["time"] == "2036-04-12T11:00:00"
    assert any(event["kind"] == "absence" for event in world.list_events(limit=5000))
    assert any(event["kind"].startswith("npc_") for event in world.list_events(limit=5000))
    count = world.event_count()
    time_after = world.snapshot()["time"]

    again = world.resume(start + timedelta(hours=3))
    assert again["advanced_minutes"] == 0
    assert world.event_count() == count
    assert world.snapshot()["time"] == time_after


def test_07b_long_absence_is_capped_and_not_replayed(tmp_path: Path) -> None:
    engine = open_world(tmp_path / "cap.db")
    try:
        start = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
        engine.resume(start)
        capped = engine.resume(start + timedelta(hours=30))
        assert capped["advanced_minutes"] == 24 * 60
        assert capped["capped"] is True
        assert engine.snapshot()["time"] == "2036-04-13T08:00:00"
        count = engine.event_count()
        replay = engine.resume(start + timedelta(hours=30))
        assert replay["advanced_minutes"] == 0
        assert engine.event_count() == count
        assert engine.snapshot()["time"] == "2036-04-13T08:00:00"
    finally:
        engine.close()


def test_07c_active_play_is_not_replayed_as_absence(world) -> None:
    start = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    world.resume(start)
    world.perform("wait", {"minutes": 60}, "play-1", now=start + timedelta(minutes=30))
    assert world.snapshot()["time"] == "2036-04-12T09:00:00"
    count = world.event_count()
    again = world.resume(start + timedelta(minutes=30))
    assert again["advanced_minutes"] == 0
    assert world.event_count() == count
    assert world.snapshot()["time"] == "2036-04-12T09:00:00"


def test_08_same_action_id_does_not_apply_twice(world) -> None:
    first = world.perform("move", {"location_id": "city_gates"}, "same-id")
    assert first["world"]["location"]["id"] == "city_gates"
    assert first["world"]["time"] == "2036-04-12T08:10:00"
    count = world.event_count()
    second = world.perform("move", {"location_id": "workshop"}, "same-id")
    assert second["replayed"] is True
    assert second["world"]["location"]["id"] == "city_gates"
    snap = world.snapshot()
    assert snap["location"]["id"] == "city_gates"
    assert snap["time"] == "2036-04-12T08:10:00"
    assert world.event_count() == count


def test_09_same_seed_reproduces_simulation(tmp_path: Path) -> None:
    def run(path: Path) -> dict:
        engine = open_world(path, seed=424242)
        try:
            engine.perform("wait", {"minutes": 60}, "seed-wait")
            engine.perform("move", {"location_id": "city_gates"}, "seed-move")
            return signature(engine)
        finally:
            engine.close()

    assert run(tmp_path / "a.db") == run(tmp_path / "b.db")


def test_10_failed_action_rolls_back(world) -> None:
    before = signature(world)
    with pytest.raises(ActionError, match="Такого места нет"):
        world.perform("move", {"location_id": "nowhere"}, "bad-move")
    assert signature(world) == before

    with pytest.raises(RuntimeError, match="injected failure"):
        world.perform("wait", {"minutes": 60}, "bad-wait", inject_failure=True)
    assert signature(world) == before

    world.perform("wait", {"minutes": 60}, "bad-wait")
    assert world.snapshot()["time"] == "2036-04-12T09:00:00"


def test_dialogue_reflects_personality_and_state(world) -> None:
    low = world.speak("marek", "talk-low")
    assert low["npc_name"] == "Марек"
    assert "есть чем торговать" in low["line"]
    assert "Торговая площадь" in low["line"]
    assert len(low["options"]) >= 2
    assert world.snapshot()["time"] == "2036-04-12T08:05:00"

    world.update_for_test(
        character={"id": "marek", "fatigue": 92, "current_action": "rest", "location_id": "market"}
    )
    high = world.speak("marek", "talk-high")
    assert "без сил" in high["line"]
    assert "Присел передохнуть" in high["line"]
    assert high["line"] != low["line"]
