from __future__ import annotations

from app.engine.effects import clamp, make_event
from app.engine.models import ActionCandidate, Character, GameEvent, Location, WorldState
from app.engine.npc import NpcBehavior
from app.engine.timekeep import in_hour_window


def rest_score(fatigue: int) -> int:
    if fatigue >= 85:
        return 300
    if fatigue >= 70:
        return 150
    if fatigue >= 55:
        return 40
    return 5


class IvarBehavior(NpcBehavior):
    def candidates(self, npc: Character, world: WorldState) -> list[ActionCandidate]:
        post = str(npc.schedule["post"])
        on_duty = in_hour_window(
            world.game_time,
            int(npc.schedule["on_duty_start"]),
            int(npc.schedule["on_duty_end"]),
        )
        alert = int(npc.schedule["threat_alert"])
        duty_score = 68 + world.threat_level
        if world.threat_level >= alert and npc.fatigue < 85:
            duty_score += 100
        candidates = [
            ActionCandidate("rest", rest_score(npc.fatigue) + (0 if on_duty else 35)),
            ActionCandidate("observe", 22 if on_duty else 30),
        ]
        if on_duty and npc.location_id == post:
            candidates.append(ActionCandidate("patrol", duty_score, reason="patrol"))
        elif on_duty:
            candidates.append(ActionCandidate("travel", duty_score, target=post, reason="patrol"))
        elif npc.location_id != post:
            candidates.append(ActionCandidate("travel", 48, target=post, reason="post"))
        return candidates

    def precondition(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> bool:
        if action.action_id == "patrol":
            post = str(npc.schedule["post"])
            return npc.location_id == post and in_hour_window(
                world.game_time,
                int(npc.schedule["on_duty_start"]),
                int(npc.schedule["on_duty_end"]),
            )
        return super().precondition(npc, world, action, locations)

    def apply(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> list[GameEvent]:
        if action.action_id != "patrol":
            return super().apply(npc, world, action, locations)
        place = locations[npc.location_id].name
        npc.fatigue = clamp(npc.fatigue + 5)
        npc.current_action = "patrol"
        npc.action_target = None
        relief = int(npc.schedule["patrol_relief"])
        world.threat_level = clamp(world.threat_level - relief)
        return [
            make_event(
                world,
                "npc_patrol",
                f"{npc.name} патрулирует «{place}» и проверяет, кто входит.",
                npc.id,
            )
        ]


class MarekBehavior(NpcBehavior):
    def candidates(self, npc: Character, world: WorldState) -> list[ActionCandidate]:
        post = str(npc.schedule["post"])
        open_now = in_hour_window(
            world.game_time,
            int(npc.schedule["open_start"]),
            int(npc.schedule["open_end"]),
        )
        candidates = [
            ActionCandidate("rest", rest_score(npc.fatigue) + (0 if open_now else 40)),
            ActionCandidate("observe", 18),
        ]
        if not open_now:
            return candidates
        if npc.location_id != post:
            candidates.append(ActionCandidate("travel", 84, target=post, reason="trade"))
            return candidates
        stock = world.market_stock
        below = int(npc.schedule["restock_below"])
        minimum = int(npc.schedule["work_min_stock"])
        if stock < below:
            candidates.append(ActionCandidate("restock", 70 + (below - stock), reason="trade"))
        if stock >= minimum:
            candidates.append(ActionCandidate("work", 58, reason="trade"))
        return candidates

    def precondition(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> bool:
        post = str(npc.schedule["post"])
        open_now = in_hour_window(
            world.game_time,
            int(npc.schedule["open_start"]),
            int(npc.schedule["open_end"]),
        )
        if action.action_id == "restock":
            return (
                open_now
                and npc.location_id == post
                and world.market_stock < int(npc.schedule["restock_below"])
            )
        if action.action_id == "work":
            return (
                open_now
                and npc.location_id == post
                and world.market_stock >= int(npc.schedule["work_min_stock"])
            )
        return super().precondition(npc, world, action, locations)

    def apply(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> list[GameEvent]:
        place = locations[npc.location_id].name
        if action.action_id == "restock":
            amount = int(npc.schedule["restock_amount"])
            world.market_stock = clamp(world.market_stock + amount)
            npc.fatigue = clamp(npc.fatigue + 5)
            npc.current_action = "restock"
            npc.action_target = None
            return [
                make_event(
                    world,
                    "npc_restock",
                    f"{npc.name} пополняет товар. Место: «{place}».",
                    npc.id,
                )
            ]
        if action.action_id == "work":
            consumed = int(npc.schedule["work_consume"])
            world.market_stock = clamp(world.market_stock - consumed)
            npc.fatigue = clamp(npc.fatigue + 4)
            npc.current_action = "work"
            npc.action_target = None
            return [
                make_event(
                    world,
                    "npc_work",
                    f"{npc.name} торгует. Запас на прилавке уменьшился.",
                    npc.id,
                )
            ]
        return super().apply(npc, world, action, locations)


class EyraBehavior(NpcBehavior):
    def candidates(self, npc: Character, world: WorldState) -> list[ActionCandidate]:
        post = str(npc.schedule["post"])
        market = str(npc.schedule["market"])
        repair_below = int(npc.schedule["repair_below"])
        needs_repair = world.grid_condition < repair_below
        has_parts = world.workshop_parts > 0
        stock_ok = world.market_stock >= int(npc.schedule["parts_cost"])
        observe_score = 36 if (not needs_repair and npc.location_id == post) else 20
        candidates = [
            ActionCandidate("rest", rest_score(npc.fatigue)),
            ActionCandidate("observe", observe_score),
        ]
        if not needs_repair:
            return candidates
        gap = repair_below - world.grid_condition
        if has_parts and npc.location_id == post:
            candidates.append(ActionCandidate("repair", 80 + gap, reason="repair"))
        elif has_parts:
            candidates.append(ActionCandidate("travel", 76 + gap, target=post, reason="repair"))
        elif npc.location_id == market and stock_ok:
            candidates.append(ActionCandidate("obtain_parts", 110 + gap // 2, reason="parts"))
        elif stock_ok:
            candidates.append(ActionCandidate("travel", 88 + gap // 2, target=market, reason="parts"))
        return candidates

    def precondition(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> bool:
        post = str(npc.schedule["post"])
        market = str(npc.schedule["market"])
        repair_below = int(npc.schedule["repair_below"])
        needs_repair = world.grid_condition < repair_below
        if action.action_id == "repair":
            return needs_repair and npc.location_id == post and world.workshop_parts > 0
        if action.action_id == "obtain_parts":
            return (
                needs_repair
                and world.workshop_parts <= 0
                and npc.location_id == market
                and world.market_stock >= int(npc.schedule["parts_cost"])
            )
        return super().precondition(npc, world, action, locations)

    def apply(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> list[GameEvent]:
        place = locations[npc.location_id].name
        if action.action_id == "repair":
            world.workshop_parts = clamp(world.workshop_parts - 1, 0, 30)
            world.grid_condition = clamp(world.grid_condition + int(npc.schedule["repair_gain"]))
            npc.fatigue = clamp(npc.fatigue + 6)
            npc.current_action = "repair"
            npc.action_target = None
            return [
                make_event(
                    world,
                    "npc_repair",
                    f"{npc.name} чинит энергосеть. Место: «{place}».",
                    npc.id,
                )
            ]
        if action.action_id == "obtain_parts":
            cost = int(npc.schedule["parts_cost"])
            gain = int(npc.schedule["parts_gain"])
            world.market_stock = clamp(world.market_stock - cost)
            world.workshop_parts = clamp(world.workshop_parts + gain, 0, 30)
            npc.fatigue = clamp(npc.fatigue + 3)
            npc.current_action = "obtain_parts"
            npc.action_target = None
            return [
                make_event(
                    world,
                    "npc_obtain_parts",
                    f"{npc.name} забирает детали у торговцев. Место: «{place}».",
                    npc.id,
                )
            ]
        return super().apply(npc, world, action, locations)
