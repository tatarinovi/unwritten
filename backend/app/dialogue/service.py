from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.content.profiles import CharacterProfile, load_profiles
from app.db.repository import Repository
from app.dialogue.context import PROMPT_FACTS, PROMPT_MESSAGES, WITNESSED_KINDS, assemble, witnessed_from_rows
from app.dialogue.schema import parse_npc_reply
from app.engine.dialogue import DialogueProvider
from app.engine.errors import ActionError
from app.engine.models import Character, WorldState
from app.engine.timekeep import format_clock, format_iso, parse_game_time
from app.llm.config import LLMSettings
from app.llm.errors import LLMFailure
from app.llm.protocol import LLMClient

logger = logging.getLogger("unwritten.dialogue")

_NAME = re.compile(
    r"(?:меня зовут|моё имя|мое имя)\s+([^\n.]{1,40})",
    re.IGNORECASE,
)


@dataclass
class PreparedLine:
    npc_id: str
    text: str
    system: str
    user: str


class LivingDialogue:
    """Free-text talk for a profile whose speech mode is ``llm``.

    Check and apply order, and where NPC movement sits in it:

    1. Under the world lock, read the save in a short transaction.
       The same action id returns the stored response. The model is
       not called, the lines are not copied again, time does not move.
    2. Reject the line when this NPC is missing or not in the player's
       location. That check is the database, not the client.
    3. Assemble context from lore, this profile, the world slice this
       NPC can know, and this NPC's memory. Close the transaction
       before any network wait. SQLite is not held while the model runs.
    4. Generate outside the transaction. One generation at a time.
       Timeout, invalid JSON, an empty reply, an unknown model, a down
       server, or a context that does not fit raise LLMFailure.
       Nothing is written, and time does not advance.
       use_template skips the model and completes with the existing
       template line. That path is a successful exchange.
    5. Open a new transaction. Repeat the action-id check and the
       location check. The world lock is still held, so an NPC tick
       cannot have moved anyone during step 4. The second location
       check stays mandatory so a later split of the lock cannot skip it.
       If the NPC is gone, raise and write nothing.
    6. Store the player line, the reply, and the player's words as
       unconfirmed claims in the same transaction as the world save.
       Those claims do not change world numbers.
    7. Advance time by five minutes. NPC ticks run here, after the
       reply is already fixed, and may move characters. They do not
       rewrite the reply.
    8. Commit the world, the events, the memory, and the idempotent
       response together. A failure rolls all of that back.
    """

    def __init__(
        self,
        content: object,
        dialogue: DialogueProvider,
        llm: LLMClient,
        settings: LLMSettings,
        profiles: dict[str, CharacterProfile] | None = None,
    ) -> None:
        self.content = content
        self.dialogue = dialogue
        self.llm = llm
        self.settings = settings
        self.profiles = load_profiles() if profiles is None else profiles
        self._generation = threading.Lock()

    def speech_mode(self, npc_id: str) -> str:
        profile = self.profiles.get(npc_id)
        if profile is None or profile.speech != "llm":
            return "template"
        return "llm"

    def prepare(
        self,
        repo: Repository,
        session: Session,
        state: WorldState,
        npc_id: str,
        text: str,
        *,
        use_template: bool,
    ) -> PreparedLine:
        cleaned = text.strip()
        if not cleaned:
            raise ActionError("Пустую реплику не отправить.")
        if len(cleaned) > 1000:
            raise ActionError("Слишком длинная реплика.")
        npc = state.characters.get(npc_id)
        if npc is None or npc.is_player:
            raise ActionError("Такого человека здесь нет.")
        if npc.location_id != state.player.location_id:
            raise ActionError("Этого человека сейчас нет рядом.")
        if self.speech_mode(npc.id) != "llm":
            raise ActionError("Этот человек отвечает только на выбранные реплики.")
        if use_template:
            return PreparedLine(npc_id=npc.id, text=cleaned, system="", user="")
        profile = self.profiles[npc.id]
        history = repo.list_dialogue(session, npc.id, PROMPT_MESSAGES)
        facts = repo.list_memory(session, npc.id, PROMPT_FACTS)
        witnessed = witnessed_from_rows(
            repo.list_events_by_kinds(session, WITNESSED_KINDS, 40),
            npc.id,
        )
        system, user = assemble(
            content=self.content,
            profile=profile,
            npc=npc,
            state=state,
            messages=history,
            facts=facts,
            player_text=cleaned,
            settings=self.settings,
            enforce_budget=True,
            witnessed=witnessed,
        )
        return PreparedLine(npc_id=npc.id, text=cleaned, system=system, user=user)

    def generate(self, prepared: PreparedLine) -> str:
        with self._generation:
            started = time.perf_counter()
            model = self.settings.model
            try:
                completion = self.llm.complete(system=prepared.system, user=prepared.user)
                model = completion.model or model
                reply = parse_npc_reply(completion.text)
            except LLMFailure as exc:
                self._log(model, started, "fail", exc.code)
                raise
            self._log(model, started, "ok", "-")
            return reply

    def fallback_line(self, npc: Character, state: WorldState) -> str:
        turn = self.dialogue.generate(npc, state, None)
        return turn.line

    def remember(
        self,
        repo: Repository,
        session: Session,
        state: WorldState,
        npc: Character,
        player_text: str,
        reply: str,
        source: str,
        request_id: str,
    ) -> None:
        moment = format_iso(state.game_time)
        repo.add_dialogue(
            session,
            npc_id=npc.id,
            role="player",
            body=player_text,
            game_time=moment,
            source="player",
            request_id=request_id,
        )
        repo.add_dialogue(
            session,
            npc_id=npc.id,
            role="npc",
            body=reply,
            game_time=moment,
            source=source,
            request_id=request_id,
        )
        repo.add_memory(
            session,
            npc_id=npc.id,
            body=player_text,
            kind="player_claim",
            source="player",
            game_time=moment,
            confirmed=False,
            request_id=request_id,
        )
        named = _called_name(player_text)
        if named:
            repo.add_memory(
                session,
                npc_id=npc.id,
                body=f"Игрок назвался: {named}",
                kind="player_name",
                source="player",
                game_time=moment,
                confirmed=False,
                request_id=request_id,
            )
        place = self.content.location_name(npc.location_id)  # type: ignore[attr-defined]
        threat = self.content.threat_label(state.threat_level)  # type: ignore[attr-defined]
        knows = set(self.profiles[npc.id].knows)
        observed = f"Разговор в месте «{place}». Угроза на периметре: {threat}."
        if "threat_level" in knows:
            observed = f"{observed} ({state.threat_level})."
        if "market_stock" in knows:
            observed = f"{observed} Запас на прилавке, который ты видишь: {state.market_stock}."
        if "grid_condition" in knows:
            observed = f"{observed} Сеть, которую ты видишь: {state.grid_condition}."
        if "workshop_parts" in knows:
            observed = f"{observed} Детали в мастерской, которые ты видишь: {state.workshop_parts}."
        repo.add_memory(
            session,
            npc_id=npc.id,
            body=observed,
            kind="world",
            source="observed",
            game_time=moment,
            confirmed=True,
            request_id=request_id,
        )
        session.flush()

    def _log(self, model: str, started: float, validation: str, error: str) -> None:
        latency = int((time.perf_counter() - started) * 1000)
        logger.info(
            "llm_result model=%s latency_ms=%s validation=%s error=%s",
            model,
            latency,
            validation,
            error,
        )


def message_views(rows: list) -> list[dict]:
    views: list[dict] = []
    for row in rows:
        moment = parse_game_time(row.game_time)
        views.append(
            {
                "id": row.id,
                "role": row.role,
                "text": row.body,
                "time": row.game_time,
                "clock": format_clock(moment),
                "source": row.source,
            }
        )
    return views


def _called_name(text: str) -> str | None:
    match = _NAME.search(text)
    if match is None:
        return None
    name = match.group(1).strip(" «»\"'")
    return name or None
