from __future__ import annotations

from pathlib import Path

from app.content.behaviors import EyraBehavior, IvarBehavior, MarekBehavior
from app.content.goals import obtain_parts_goal, security_goal
from app.content.node17 import Node17Content
from app.engine.goals import ensure_active_goal, evaluate_goals, has_active_goal
from app.engine.models import ActionCandidate
from app.engine.npc import NpcBehavior, run_npc_tick
from app.engine.rng import CounterRNG
from tests.conftest import open_world
from tests.test_world import npc_by_id


def _active(npc: dict, goal_id: str) -> list[dict]:
    return [goal for goal in npc["goals"] if goal["id"] == goal_id and goal["status"] == "active"]


def _score(behavior, npc, world, action_id: str) -> int:
    found = [item for item in behavior.candidates(npc, world) if item.action_id == action_id]
    assert found, action_id
    return found[0].score


def _prime(world, *, stock: int, eyra_at: str, marek_at: str, parts: int = 0, grid: int = 30) -> None:
    world.update_for_test(
        character={"id": "eyra", "location_id": eyra_at, "fatigue": 10, "current_action": "observe"},
        world_fields={"grid_condition": grid, "workshop_parts": parts, "market_stock": stock},
    )
    world.update_for_test(
        character={"id": "marek", "location_id": marek_at, "fatigue": 96, "current_action": "rest"},
    )


def test_long_term_goals_raise_matching_scores() -> None:
    content = Node17Content()
    state = content.build_initial(1)
    ivar = state.characters["ivar"]
    marek = state.characters["marek"]
    eyra = state.characters["eyra"]
    state.grid_condition = 40
    state.workshop_parts = 4
    state.market_stock = 42

    ivar.goals = []
    patrol_without = _score(IvarBehavior(), ivar, state, "patrol")
    ivar.goals = [security_goal()]
    patrol_with = _score(IvarBehavior(), ivar, state, "patrol")
    assert patrol_with > patrol_without

    marek.goals = []
    restock_without = _score(MarekBehavior(), marek, state, "restock")
    marek.goals = [content.build_initial(1).characters["marek"].goals[0]]
    restock_with = _score(MarekBehavior(), marek, state, "restock")
    assert restock_with > restock_without

    eyra.goals = []
    repair_without = _score(EyraBehavior(), eyra, state, "repair")
    eyra.goals = [content.build_initial(1).characters["eyra"].goals[0]]
    repair_with = _score(EyraBehavior(), eyra, state, "repair")
    assert repair_with > repair_without

    state.workshop_parts = 0
    state.grid_condition = 30
    eyra.goals = []
    seek_without = _score(EyraBehavior(), eyra, state, "travel")
    ensure_active_goal(eyra, obtain_parts_goal())
    seek_with = _score(EyraBehavior(), eyra, state, "travel")
    assert seek_with > seek_without


def test_profit_floor_accepts_at_20_and_refuses_at_19() -> None:
    state = Node17Content().build_initial(1)
    eyra = state.characters["eyra"]
    marek = state.characters["marek"]
    ensure_active_goal(eyra, obtain_parts_goal())
    state.workshop_parts = 0
    behavior = EyraBehavior()
    state.market_stock = 20
    assert behavior._marek_accepts(eyra, marek, state) is True
    state.market_stock = 19
    assert behavior._marek_accepts(eyra, marek, state) is False
    marek.goals = []
    state.market_stock = 8
    assert behavior._marek_accepts(eyra, marek, state) is True
    state.market_stock = 7
    assert behavior._marek_accepts(eyra, marek, state) is False


def test_obtain_goal_completes_only_from_workshop_stock() -> None:
    state = Node17Content().build_initial(1)
    eyra = state.characters["eyra"]
    ensure_active_goal(eyra, obtain_parts_goal())
    state.workshop_parts = 0
    evaluate_goals(state)
    assert has_active_goal(eyra, "obtain_parts")
    state.workshop_parts = 1
    evaluate_goals(state)
    assert not has_active_goal(eyra, "obtain_parts")


def test_short_term_goal_appears_only_when_parts_are_missing(world) -> None:
    _prime(world, stock=40, eyra_at="workshop", marek_at="market", parts=0, grid=30)
    before = npc_by_id(world, "eyra")
    assert _active(before, "obtain_parts") == []

    world.perform("wait", {"minutes": 10}, "goal-appears")
    eyra = npc_by_id(world, "eyra")
    assert len(_active(eyra, "obtain_parts")) == 1
    assert eyra["goal"] == "Достать детали для сети"
    goal = _active(eyra, "obtain_parts")[0]
    assert goal["kind"] == "short_term"
    assert goal["condition"] == "workshop_parts_at_least"
    assert goal["threshold"] == 1

    world.perform("wait", {"minutes": 10}, "goal-no-duplicate")
    again = npc_by_id(world, "eyra")
    assert len(_active(again, "obtain_parts")) == 1


def test_short_term_goal_stays_hidden_when_the_grid_is_fine(world) -> None:
    _prime(world, stock=40, eyra_at="workshop", marek_at="market", parts=0, grid=90)
    world.perform("wait", {"minutes": 10}, "grid-fine")
    eyra = npc_by_id(world, "eyra")
    assert _active(eyra, "obtain_parts") == []
    assert eyra["goal"] == "Держать энергосеть"


def test_eyra_travels_to_marek_and_does_not_transfer_while_apart(world) -> None:
    _prime(world, stock=40, eyra_at="workshop", marek_at="city_gates", parts=0, grid=30)
    world.perform("wait", {"minutes": 10}, "travel-to-marek")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    assert eyra["location_id"] == "city_gates"
    assert eyra["carried_parts"] == 0
    assert settlement["market_stock"] == 40
    assert settlement["workshop_parts"] == 0
    moves = [
        event
        for event in world.list_events()
        if event["kind"] == "npc_move" and event["actor_id"] == "eyra"
    ]
    assert len(moves) == 1
    assert moves[0]["data"]["from"] == "workshop"
    assert moves[0]["data"]["to"] == "city_gates"
    assert moves[0]["data"]["reason"] == "parts"
    kinds = {event["kind"] for event in world.list_events()}
    assert "npc_parts_handover" not in kinds
    assert "npc_parts_refused" not in kinds


def test_request_apart_does_not_move_resources() -> None:
    state = Node17Content().build_initial(1)
    eyra = state.characters["eyra"]
    marek = state.characters["marek"]
    marek.location_id = "city_gates"
    state.market_stock = 40
    state.workshop_parts = 0
    ensure_active_goal(eyra, obtain_parts_goal())
    action = ActionCandidate("request_parts", 100, target_character_id="marek", reason="parts")
    events = EyraBehavior().apply(eyra, state, action, Node17Content().locations())
    assert events == []
    assert state.market_stock == 40
    assert state.workshop_parts == 0
    assert eyra.carried_parts == 0
    assert eyra.location_id == "workshop"


def test_engine_blocks_targeted_action_when_characters_are_apart() -> None:
    content = Node17Content()
    state = content.build_initial(1)
    state.characters["eyra"].location_id = "workshop"
    state.characters["marek"].location_id = "city_gates"
    state.characters["ivar"].fatigue = 96
    state.characters["marek"].fatigue = 96
    state.market_stock = 40

    class Greedy(NpcBehavior):
        def candidates(self, npc, world):
            return [ActionCandidate("request_parts", 500, target_character_id="marek")]

        def precondition(self, npc, world, action, locations) -> bool:
            return True

        def apply(self, npc, world, action, locations):
            world.market_stock -= 8
            npc.carried_parts += 4
            return []

    behaviors = {"ivar": IvarBehavior(), "marek": MarekBehavior(), "eyra": Greedy()}
    run_npc_tick(state, behaviors, content.locations(), CounterRNG(1, 0))
    assert state.market_stock == 40
    assert state.characters["eyra"].carried_parts == 0

    state.characters["eyra"].location_id = "city_gates"
    run_npc_tick(state, behaviors, content.locations(), CounterRNG(1, 0))
    assert state.market_stock == 32
    assert state.characters["eyra"].carried_parts == 4


def test_handover_then_delivery_changes_stock_only_at_each_step(world) -> None:
    _prime(world, stock=40, eyra_at="market", marek_at="market", parts=0, grid=30)
    world.perform("wait", {"minutes": 10}, "handover")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    assert settlement["market_stock"] == 32
    assert settlement["workshop_parts"] == 0
    assert eyra["carried_parts"] == 4
    assert eyra["location_id"] == "market"
    assert len(_active(eyra, "obtain_parts")) == 1
    outcomes = [(event["kind"], event["data"].get("outcome")) for event in world.list_events()]
    assert ("npc_parts_request", "requested") in outcomes
    assert ("npc_parts_handover", "handover") in outcomes
    assert ("npc_parts_delivery", "delivered") not in outcomes

    world.update_for_test(character={"id": "eyra", "location_id": "workshop", "fatigue": 10})
    world.update_for_test(character={"id": "marek", "fatigue": 96, "location_id": "market"})
    world.perform("wait", {"minutes": 10}, "deliver")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    assert eyra["location_id"] == "workshop"
    assert eyra["carried_parts"] == 0
    assert settlement["workshop_parts"] == 4
    assert settlement["market_stock"] == 32
    assert _active(eyra, "obtain_parts") == []
    completed = [goal for goal in eyra["goals"] if goal["id"] == "obtain_parts"]
    assert completed and completed[0]["status"] == "completed"
    assert eyra["goal"] == "Держать энергосеть"
    delivered = [event for event in world.list_events() if event["kind"] == "npc_parts_delivery"]
    assert len(delivered) == 1
    assert delivered[0]["data"]["outcome"] == "delivered"
    assert delivered[0]["data"]["workshop_parts_delta"] == 4


def _hold_refused_stock(world, ticks: int, tag: str) -> None:
    """Keep the refusal line true for `ticks` ten-minute steps.

    Marek is held too tired to restock, and stock is put back to 19 before
    each tick. Either change would otherwise clear the refusal and hide a loop.
    Eyra's own action and fatigue are left alone.
    """
    for index in range(ticks):
        world.update_for_test(
            world_fields={"market_stock": 19, "workshop_parts": 0, "grid_condition": 30},
        )
        world.update_for_test(
            character={"id": "marek", "location_id": "market", "fatigue": 96, "current_action": "rest"},
        )
        world.perform("wait", {"minutes": 10}, f"{tag}-{index}")


def _part_kinds(world) -> list[str]:
    return [event["kind"] for event in world.list_events(limit=5000)]


def test_tc01_refusal_at_stock_19(world) -> None:
    _prime(world, stock=19, eyra_at="market", marek_at="market", parts=0, grid=30)
    world.perform("wait", {"minutes": 10}, "tc01-refuse")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    assert settlement["market_stock"] == 19
    assert settlement["workshop_parts"] == 0
    assert eyra["carried_parts"] == 0
    kinds = _part_kinds(world)
    assert kinds.count("npc_parts_request") == 1
    assert kinds.count("npc_parts_refused") == 1
    assert "npc_parts_handover" not in kinds
    assert len(_active(eyra, "obtain_parts")) == 1
    assert eyra["parts_result"] == "refused"


def test_tc02_no_infinite_refusal_loop(world) -> None:
    _prime(world, stock=19, eyra_at="market", marek_at="market", parts=0, grid=30)
    _hold_refused_stock(world, 6 * 6, "tc02")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    kinds = _part_kinds(world)
    assert kinds.count("npc_parts_request") == 1
    assert kinds.count("npc_parts_refused") == 1
    assert "npc_parts_handover" not in kinds
    assert eyra["current_action"] != "request_parts"
    assert eyra["parts_result"] == "refused"
    assert eyra["carried_parts"] == 0
    assert settlement["market_stock"] == 19
    assert settlement["workshop_parts"] == 0
    assert len(_active(eyra, "obtain_parts")) == 1
    assert eyra["goal"] == "Достать детали для сети"


def test_tc03_retry_when_stock_reaches_accept_line(world) -> None:
    _prime(world, stock=19, eyra_at="market", marek_at="market", parts=0, grid=30)
    world.perform("wait", {"minutes": 10}, "tc03-refuse")
    assert npc_by_id(world, "eyra")["parts_result"] == "refused"
    world.update_for_test(world_fields={"market_stock": 20, "workshop_parts": 0, "grid_condition": 30})
    world.update_for_test(
        character={"id": "marek", "location_id": "market", "fatigue": 96, "current_action": "rest"},
    )
    world.update_for_test(character={"id": "eyra", "location_id": "market", "fatigue": 10})
    world.perform("wait", {"minutes": 10}, "tc03-retry")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    assert settlement["market_stock"] == 12
    assert settlement["workshop_parts"] == 0
    assert eyra["carried_parts"] == 4
    assert eyra["parts_result"] == "handover"
    kinds = _part_kinds(world)
    assert kinds.count("npc_parts_handover") == 1
    assert len(_active(eyra, "obtain_parts")) == 1


def test_tc04_refusal_latch_persists(tmp_path: Path) -> None:
    path = tmp_path / "latch.db"
    engine = open_world(path)
    try:
        _prime(engine, stock=19, eyra_at="market", marek_at="market", parts=0, grid=30)
        engine.perform("wait", {"minutes": 10}, "tc04-refuse")
        assert npc_by_id(engine, "eyra")["parts_result"] == "refused"
    finally:
        engine.close()

    restored = open_world(path)
    try:
        eyra = npc_by_id(restored, "eyra")
        assert eyra["parts_result"] == "refused"
        assert len(_active(eyra, "obtain_parts")) == 1
        before = _part_kinds(restored).count("npc_parts_request")
        assert before == 1
        _hold_refused_stock(restored, 6 * 6, "tc04")
        eyra = npc_by_id(restored, "eyra")
        kinds = _part_kinds(restored)
        assert kinds.count("npc_parts_request") == before
        assert kinds.count("npc_parts_refused") == 1
        assert eyra["parts_result"] == "refused"
        assert eyra["current_action"] != "request_parts"
        assert eyra["carried_parts"] == 0
        assert restored.snapshot()["settlement"]["market_stock"] == 19
    finally:
        restored.close()


def test_tc05_regression_transfer_delivery_goals_and_time(world) -> None:
    content = Node17Content()
    state = content.build_initial(1)
    eyra_state = state.characters["eyra"]
    state.workshop_parts = 0
    state.grid_condition = 30
    state.market_stock = 40
    eyra_state.goals = [goal for goal in eyra_state.goals if goal.id != "obtain_parts"]
    seek_without = _score(EyraBehavior(), eyra_state, state, "travel")
    ensure_active_goal(eyra_state, obtain_parts_goal())
    seek_with = _score(EyraBehavior(), eyra_state, state, "travel")
    assert seek_with > seek_without

    _prime(world, stock=40, eyra_at="market", marek_at="market", parts=0, grid=30)
    world.perform("wait", {"minutes": 10}, "tc05-handover")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    assert world.snapshot()["time"] == "2036-04-12T08:10:00"
    assert settlement["market_stock"] == 32
    assert settlement["workshop_parts"] == 0
    assert eyra["carried_parts"] == 4
    assert eyra["goal"] == "Достать детали для сети"
    assert len(_active(eyra, "obtain_parts")) == 1

    world.update_for_test(character={"id": "eyra", "location_id": "workshop", "fatigue": 10})
    world.update_for_test(character={"id": "marek", "fatigue": 96, "location_id": "market"})
    world.perform("wait", {"minutes": 10}, "tc05-deliver")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    assert world.snapshot()["time"] == "2036-04-12T08:20:00"
    assert eyra["carried_parts"] == 0
    assert settlement["workshop_parts"] == 4
    assert settlement["market_stock"] == 32
    assert _active(eyra, "obtain_parts") == []
    assert eyra["goal"] == "Держать энергосеть"
    delivered = [event for event in world.list_events(limit=5000) if event["kind"] == "npc_parts_delivery"]
    assert len(delivered) == 1

    world.perform("wait", {"minutes": 60}, "tc05-hour")
    assert world.snapshot()["time"] == "2036-04-12T09:20:00"


def test_refusal_leaves_stock_and_workshop_unchanged(world) -> None:
    _prime(world, stock=15, eyra_at="market", marek_at="market", parts=0, grid=30)
    world.perform("wait", {"minutes": 10}, "refuse")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    assert settlement["market_stock"] == 15
    assert settlement["workshop_parts"] == 0
    assert eyra["carried_parts"] == 0
    outcomes = [(event["kind"], event["data"].get("outcome")) for event in world.list_events()]
    assert ("npc_parts_request", "requested") in outcomes
    assert ("npc_parts_refused", "refused") in outcomes
    assert ("npc_parts_handover", "handover") not in outcomes
    assert len(_active(eyra, "obtain_parts")) == 1


def test_goal_stays_when_the_grid_recovers_without_delivery(world) -> None:
    _prime(world, stock=10, eyra_at="workshop", marek_at="city_gates", parts=0, grid=30)
    world.perform("wait", {"minutes": 10}, "cause-on")
    assert len(_active(npc_by_id(world, "eyra"), "obtain_parts")) == 1
    world.update_for_test(world_fields={"grid_condition": 96, "workshop_parts": 0, "market_stock": 10})
    world.update_for_test(character={"id": "marek", "fatigue": 96, "location_id": "city_gates"})
    world.perform("wait", {"minutes": 10}, "cause-off")
    eyra = npc_by_id(world, "eyra")
    settlement = world.snapshot()["settlement"]
    assert len(_active(eyra, "obtain_parts")) == 1
    assert settlement["workshop_parts"] == 0
    assert settlement["market_stock"] == 10
    assert eyra["carried_parts"] == 0


def test_exchange_persists_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "social.db"
    engine = open_world(path)
    try:
        _prime(engine, stock=40, eyra_at="market", marek_at="market", parts=0, grid=30)
        engine.perform("wait", {"minutes": 10}, "persist-handover")
    finally:
        engine.close()

    restored = open_world(path)
    try:
        eyra = npc_by_id(restored, "eyra")
        settlement = restored.snapshot()["settlement"]
        assert settlement["market_stock"] == 32
        assert settlement["workshop_parts"] == 0
        assert eyra["carried_parts"] == 4
        assert eyra["location_id"] == "market"
        assert len(_active(eyra, "obtain_parts")) == 1
    finally:
        restored.close()


def test_same_seed_same_social_outcome(tmp_path: Path) -> None:
    def run(path: Path, seed: int) -> tuple:
        engine = open_world(path, seed=seed)
        try:
            _prime(engine, stock=40, eyra_at="market", marek_at="market", parts=0, grid=30)
            engine.perform("wait", {"minutes": 10}, "seed-social")
            eyra = npc_by_id(engine, "eyra")
            settlement = engine.snapshot()["settlement"]
            goal = _active(eyra, "obtain_parts")[0]
            return (
                settlement["market_stock"],
                settlement["workshop_parts"],
                eyra["carried_parts"],
                eyra["location_id"],
                goal["status"],
            )
        finally:
            engine.close()

    assert run(tmp_path / "a.db", 17041) == run(tmp_path / "b.db", 17041)
    assert run(tmp_path / "c.db", 17041) == run(tmp_path / "d.db", 99991)
