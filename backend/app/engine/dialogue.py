from __future__ import annotations

from typing import Protocol

from app.engine.errors import ActionError
from app.engine.models import Character, DialogueTurn, WorldState


class DialogueSource(Protocol):
    def dialogue_bundle(self) -> dict: ...

    def location_name(self, location_id: str) -> str: ...

    def stock_label(self, value: int) -> str: ...

    def grid_label(self, value: int) -> str: ...

    def threat_label(self, value: int) -> str: ...

    def fatigue_band(self, fatigue: int) -> str: ...


class DialogueProvider(Protocol):
    """Asked by the World Engine for a line. It does not advance time or save state.

    TemplateDialogueProvider is the v0.0.1 implementation. A later adapter can
    call an LLM and return DialogueTurn without changes to the World Engine.
    """

    def generate(
        self,
        npc: Character,
        world: WorldState,
        reply_id: str | None,
    ) -> DialogueTurn: ...


class TemplateDialogueProvider:
    def __init__(self, source: DialogueSource) -> None:
        self.source = source

    def generate(
        self,
        npc: Character,
        world: WorldState,
        reply_id: str | None,
    ) -> DialogueTurn:
        bundle = self.source.dialogue_bundle()
        pack = bundle.get(npc.id)
        if pack is None:
            raise ActionError("С этим человеком не о чем говорить.")
        band = self.source.fatigue_band(npc.fatigue)
        values = {
            "location": self.source.location_name(npc.location_id),
            "stock_label": self.source.stock_label(world.market_stock),
            "grid_label": self.source.grid_label(world.grid_condition),
            "threat_label": self.source.threat_label(world.threat_level),
        }
        if reply_id is None:
            opener = pack["openers"][band]
            action_line = pack["actions"].get(npc.current_action, pack["actions"]["default"])
            line = f"{opener} {action_line.format(**values)}"
        else:
            replies = pack["replies"]
            if reply_id not in replies:
                raise ActionError("Такого ответа нет.")
            line = replies[reply_id][band].format(**values)
        options = [{"id": item["id"], "label": item["label"]} for item in pack["options"]]
        return DialogueTurn(npc_id=npc.id, npc_name=npc.name, line=line, options=options)
