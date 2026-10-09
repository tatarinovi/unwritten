from __future__ import annotations


def test_world_and_npcs(client) -> None:
    world = client.get("/api/world")
    assert world.status_code == 200
    body = world.json()
    assert body["time"] == "2036-04-12T08:00:00"
    assert body["location"]["name"] == "Торговая площадь"
    assert body["player"]["name"] == "Саша Ковалёв"
    assert any(action["type"] == "wait" and action["params"]["minutes"] == 60 for action in body["available_actions"])

    npcs = client.get("/api/npcs")
    assert npcs.status_code == 200
    assert [npc["name"] for npc in npcs.json()] == ["Ивар", "Марек", "Эйра"]


def test_move_is_idempotent_via_api(client) -> None:
    first = client.post(
        "/api/actions",
        json={"action_id": "api-move", "type": "move", "params": {"location_id": "workshop"}},
    )
    assert first.status_code == 200
    assert first.json()["replayed"] is False
    assert first.json()["world"]["location"]["id"] == "workshop"
    assert first.json()["world"]["time"] == "2036-04-12T08:10:00"

    second = client.post(
        "/api/actions",
        json={"action_id": "api-move", "type": "move", "params": {"location_id": "city_gates"}},
    )
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    current = client.get("/api/world").json()
    assert current["location"]["id"] == "workshop"
    assert current["time"] == "2036-04-12T08:10:00"


def test_invalid_move_does_not_change_world(client) -> None:
    before = client.get("/api/world").json()
    events_before = client.get("/api/events").json()
    response = client.post(
        "/api/actions",
        json={"action_id": "api-bad", "type": "move", "params": {"location_id": "moon"}},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Такого места нет."
    after = client.get("/api/world").json()
    events_after = client.get("/api/events").json()
    assert after["time"] == before["time"]
    assert after["location"]["id"] == before["location"]["id"]
    assert events_after == events_before


def test_dialogue_and_reply_advance_time(client) -> None:
    absent = client.post("/api/dialogue", json={"action_id": "no-ivar", "npc_id": "ivar"})
    assert absent.status_code == 400
    assert client.get("/api/world").json()["time"] == "2036-04-12T08:00:00"

    opened = client.post("/api/dialogue", json={"action_id": "talk-1", "npc_id": "marek"})
    assert opened.status_code == 200
    body = opened.json()
    assert body["npc_name"] == "Марек"
    assert body["line"]
    assert body["world"]["time"] == "2036-04-12T08:05:00"
    reply_id = body["options"][0]["id"]

    replied = client.post(
        "/api/dialogue",
        json={"action_id": "talk-2", "npc_id": "marek", "reply_id": reply_id},
    )
    assert replied.status_code == 200
    assert replied.json()["line"]
    assert replied.json()["world"]["time"] == "2036-04-12T08:10:00"

    replay = client.post("/api/dialogue", json={"action_id": "talk-2", "npc_id": "marek", "reply_id": reply_id})
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert client.get("/api/world").json()["time"] == "2036-04-12T08:10:00"


def test_resume_catches_up_once(client) -> None:
    first = client.post("/api/session/resume", json={"now": "2026-06-01T08:00:00Z"})
    assert first.status_code == 200
    assert first.json()["advanced_minutes"] == 0

    second = client.post("/api/session/resume", json={"now": "2026-06-01T11:00:00Z"})
    assert second.status_code == 200
    assert second.json()["advanced_minutes"] == 180
    assert second.json()["world"]["time"] == "2036-04-12T11:00:00"

    third = client.post("/api/session/resume", json={"now": "2026-06-01T11:00:00Z"})
    assert third.status_code == 200
    assert third.json()["advanced_minutes"] == 0
    assert client.get("/api/world").json()["time"] == "2036-04-12T11:00:00"
    kinds = {event["kind"] for event in client.get("/api/events?limit=500").json()}
    assert "absence" in kinds
    assert any(kind.startswith("npc_") for kind in kinds)
