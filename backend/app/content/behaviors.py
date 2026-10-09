from __future__ import annotations

from app.content.goals import GRID_ID, OBTAIN_PARTS_ID, PROFIT_ID, SECURITY_ID
from app.engine.effects import clamp, make_event
from app.engine.goals import has_active_goal, interaction_allowed
from app.engine.models import ActionCandidate, Character, GameEvent, Location, WorldState
from app.engine.npc import NpcBehavior
from app.engine.timekeep import in_hour_window

# Active long-term goals raise the matching scores. The gap is larger than a
# tie-break roll, so a character who is pursuing the goal prefers that work
# over the same character who is not.
SECURITY_FOCUS = 20
PROFIT_FOCUS = 16
GRID_FOCUS = 18
PARTS_FOCUS = 20


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
        security_focus = SECURITY_FOCUS if has_active_goal(npc, SECURITY_ID) else 0
        duty_score = 68 + world.threat_level + security_focus
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
            candidates.append(ActionCandidate("travel", 48 + security_focus, target=post, reason="post"))
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
        profit_focus = PROFIT_FOCUS if has_active_goal(npc, PROFIT_ID) else 0
        candidates = [
            ActionCandidate("rest", rest_score(npc.fatigue) + (0 if open_now else 40)),
            ActionCandidate("observe", 18),
        ]
        if not open_now:
            return candidates
        if npc.location_id != post:
            candidates.append(ActionCandidate("travel", 84 + profit_focus, target=post, reason="trade"))
            return candidates
        stock = world.market_stock
        below = int(npc.schedule["restock_below"])
        minimum = int(npc.schedule["work_min_stock"])
        if stock < below:
            candidates.append(ActionCandidate("restock", 70 + (below - stock) + profit_focus, reason="trade"))
        if stock >= minimum:
            candidates.append(ActionCandidate("work", 58 + profit_focus, reason="trade"))
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
        repair_below = int(npc.schedule["repair_below"])
        needs_repair = world.grid_condition < repair_below
        has_parts = world.workshop_parts > 0
        carrying = npc.carried_parts > 0
        gap = max(0, repair_below - world.grid_condition)
        grid_focus = GRID_FOCUS if has_active_goal(npc, GRID_ID) else 0
        parts_focus = PARTS_FOCUS if has_active_goal(npc, OBTAIN_PARTS_ID) else 0
        observe_score = 36 if (not needs_repair and not carrying and npc.location_id == post) else 20
        candidates = [
            ActionCandidate("rest", rest_score(npc.fatigue)),
            ActionCandidate("observe", observe_score),
        ]
        if carrying:
            # Parts in her hands are not workshop stock. She walks them home.
            deliver_score = 130 + parts_focus
            if npc.location_id == post:
                candidates.append(ActionCandidate("deliver_parts", deliver_score, reason="deliver"))
            else:
                candidates.append(ActionCandidate("travel", deliver_score, target=post, reason="deliver"))
            return candidates
        if needs_repair and has_parts:
            repair_score = 80 + gap + grid_focus
            if npc.location_id == post:
                candidates.append(ActionCandidate("repair", repair_score, reason="repair"))
            else:
                candidates.append(ActionCandidate("travel", repair_score - 4, target=post, reason="repair"))
            return candidates
        seeking = has_active_goal(npc, OBTAIN_PARTS_ID) or (needs_repair and not has_parts)
        if not seeking:
            return candidates
        marek = world.characters.get("marek")
        if marek is None or marek.is_player:
            return candidates
        seek = 100 + gap // 2 + parts_focus
        if marek.location_id == npc.location_id:
            candidates.append(
                ActionCandidate(
                    "request_parts",
                    seek,
                    target_character_id=marek.id,
                    reason="parts",
                )
            )
        else:
            candidates.append(ActionCandidate("travel", seek, target=marek.location_id, reason="parts"))
        return candidates

    def precondition(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
        locations: dict[str, Location],
    ) -> bool:
        post = str(npc.schedule["post"])
        repair_below = int(npc.schedule["repair_below"])
        needs_repair = world.grid_condition < repair_below
        if action.action_id == "repair":
            return needs_repair and npc.location_id == post and world.workshop_parts > 0
        if action.action_id == "deliver_parts":
            return npc.carried_parts > 0 and npc.location_id == post
        if action.action_id == "request_parts":
            if not interaction_allowed(npc, world, action.target_character_id):
                return False
            if action.target_character_id != "marek":
                return False
            if npc.carried_parts > 0 or world.workshop_parts > 0:
                return False
            return has_active_goal(npc, OBTAIN_PARTS_ID) or needs_repair
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
        if action.action_id == "deliver_parts":
            return self._deliver(npc, world, locations)
        if action.action_id == "request_parts":
            return self._request(npc, world, action)
        return super().apply(npc, world, action, locations)

    def _request(
        self,
        npc: Character,
        world: WorldState,
        action: ActionCandidate,
    ) -> list[GameEvent]:
        # Apart, missing, or the player: do not move stock, carried parts, or workshop parts.
        if not interaction_allowed(npc, world, action.target_character_id):
            return []
        marek = world.characters.get(action.target_character_id or "")
        if marek is None:
            return []
        request = make_event(
            world,
            "npc_parts_request",
            f"{npc.name} просит у {marek.name} детали для сети.",
            npc.id,
            {"outcome": "requested", "target_character_id": marek.id},
        )
        if not self._eyra_needs_bundle(npc, world):
            return []
        npc.current_action = "request_parts"
        npc.action_target = marek.id
        npc.fatigue = clamp(npc.fatigue + 2)
        if not self._marek_accepts(npc, marek, world):
            return [
                request,
                make_event(
                    world,
                    "npc_parts_refused",
                    f"{marek.name} отказывает: для торговли запас слишком мал.",
                    marek.id,
                    {
                        "outcome": "refused",
                        "target_character_id": npc.id,
                        "market_stock": world.market_stock,
                        "workshop_parts": world.workshop_parts,
                        "carried_parts": npc.carried_parts,
                    },
                ),
            ]
        cost = int(npc.schedule["parts_cost"])
        gain = int(npc.schedule["parts_gain"])
        world.market_stock = clamp(world.market_stock - cost)
        npc.carried_parts += gain
        npc.current_action = "carry_parts"
        npc.fatigue = clamp(npc.fatigue + 1)
        return [
            request,
            make_event(
                world,
                "npc_parts_handover",
                f"{marek.name} отдаёт {npc.name} детали. Она несёт их с собой.",
                npc.id,
                {
                    "outcome": "handover",
                    "target_character_id": marek.id,
                    "market_stock_delta": -cost,
                    "carried_parts": gain,
                    "owner_id": npc.id,
                    "location_id": npc.location_id,
                },
            ),
        ]

    def _eyra_needs_bundle(self, eyra: Character, world: WorldState) -> bool:
        # Short-term goal, or the grid is down and the workshop is empty.
        # Carried parts and workshop stock are not another request.
        if eyra.carried_parts > 0 or world.workshop_parts > 0:
            return False
        if has_active_goal(eyra, OBTAIN_PARTS_ID):
            return True
        return world.grid_condition < int(eyra.schedule["repair_below"])

    def _marek_accepts(self, eyra: Character, marek: Character, world: WorldState) -> bool:
        # Marek answers from Eyra's need, his stock, and his profit goal.
        # Fully determined. No roll.
        #
        # The bundle is the prototype's small integers: parts_cost (8) leaves
        # market stock and becomes parts_gain (4) carried by Eyra. Workshop
        # stock does not change on this tick.
        #
        # Profit goal active: accept only when market_stock - parts_cost
        # >= work_min_stock (12). After the gift he can still trade.
        # Stock 20 accepts (12 left). Stock 19 refuses. Below that floor the
        # request is refused and nothing moves.
        #
        # Profit goal not active: accept when market_stock >= parts_cost.
        if not self._eyra_needs_bundle(eyra, world):
            return False
        cost = int(eyra.schedule["parts_cost"])
        stock = world.market_stock
        if has_active_goal(marek, PROFIT_ID):
            floor = int(marek.schedule["work_min_stock"])
            return stock - cost >= floor
        return stock >= cost

    def _deliver(
        self,
        npc: Character,
        world: WorldState,
        locations: dict[str, Location],
    ) -> list[GameEvent]:
        post = str(npc.schedule["post"])
        if npc.carried_parts <= 0 or npc.location_id != post:
            return []
        gain = npc.carried_parts
        world.workshop_parts = clamp(world.workshop_parts + gain, 0, 30)
        npc.carried_parts = 0
        npc.fatigue = clamp(npc.fatigue + 3)
        npc.current_action = "deliver_parts"
        npc.action_target = None
        place = locations[npc.location_id].name
        return [
            make_event(
                world,
                "npc_parts_delivery",
                f"{npc.name} приносит детали в мастерскую. Место: «{place}».",
                npc.id,
                {
                    "outcome": "delivered",
                    "workshop_parts_delta": gain,
                    "location_id": npc.location_id,
                },
            )
        ]
