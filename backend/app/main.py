from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.content.node17 import Node17Content
from app.db.repository import Repository
from app.dialogue.service import LivingDialogue
from app.engine.dialogue import TemplateDialogueProvider
from app.engine.world import WorldEngine
from app.llm.config import LLMSettings, load_settings
from app.llm.ollama import OllamaClient
from app.llm.protocol import LLMClient


def configure_dialogue_logging() -> None:
    """Emit latency and validation lines. Dialogue text is not logged."""
    dialogue_log = logging.getLogger("unwritten.dialogue")
    dialogue_log.setLevel(logging.INFO)
    if dialogue_log.handlers:
        return
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    dialogue_log.addHandler(handler)
    dialogue_log.propagate = False


def default_database_url() -> str:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + (data_dir / "unwritten.db").resolve().as_posix()


def build_world(
    database_url: str,
    seed: int | None = None,
    llm: LLMClient | None = None,
    settings: LLMSettings | None = None,
) -> WorldEngine:
    repository = Repository(database_url)
    repository.create_all()
    content = Node17Content()
    dialogue = TemplateDialogueProvider(content)
    resolved = settings or load_settings()
    living = LivingDialogue(content, dialogue, llm or OllamaClient(resolved), resolved)
    engine = WorldEngine(repository, content, dialogue, living)
    engine.ensure_initialized(seed=seed)
    return engine


def create_app(database_url: str | None = None, llm: LLMClient | None = None) -> FastAPI:
    configure_dialogue_logging()
    engine = build_world(database_url or default_database_url(), llm=llm)
    app = FastAPI(title="UNWRITTEN", version="0.0.3.1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.world = engine
    app.include_router(router)
    return app


app = create_app()
