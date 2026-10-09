from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.engine.errors import ActionError
from app.engine.world import WorldEngine

router = APIRouter()


class ActionRequest(BaseModel):
    action_id: str = Field(min_length=1, max_length=80)
    type: Literal["move", "look", "wait"]
    params: dict[str, Any] = Field(default_factory=dict)
    now: datetime | None = None


class DialogueRequest(BaseModel):
    action_id: str = Field(min_length=1, max_length=80)
    npc_id: str = Field(min_length=1, max_length=32)
    reply_id: str | None = None
    now: datetime | None = None


class ResumeRequest(BaseModel):
    now: datetime


def _world(request: Request) -> WorldEngine:
    return request.app.state.world


@router.get("/api/health")
def health() -> dict[str, str]:
    return {"name": "UNWRITTEN", "version": "0.0.1"}


@router.get("/api/world")
def get_world(request: Request) -> dict[str, Any]:
    return _world(request).snapshot()


@router.get("/api/npcs")
def get_npcs(request: Request) -> list[dict[str, Any]]:
    return _world(request).list_npcs()


@router.get("/api/events")
def get_events(request: Request, limit: int = Query(default=80, ge=1, le=500)) -> list[dict[str, Any]]:
    return _world(request).list_events(limit)


@router.post("/api/actions")
def post_action(body: ActionRequest, request: Request) -> dict[str, Any]:
    try:
        return _world(request).perform(body.type, body.params, body.action_id, body.now)
    except ActionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


@router.post("/api/dialogue")
def post_dialogue(body: DialogueRequest, request: Request) -> dict[str, Any]:
    try:
        return _world(request).speak(body.npc_id, body.action_id, body.reply_id, body.now)
    except ActionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


@router.post("/api/session/resume")
def post_resume(body: ResumeRequest, request: Request) -> dict[str, Any]:
    return _world(request).resume(body.now)
