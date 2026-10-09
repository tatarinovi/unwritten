from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.content.node17 import Node17Content
from app.db.repository import Repository
from app.engine.dialogue import TemplateDialogueProvider
from app.engine.world import WorldEngine


def default_database_url() -> str:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + (data_dir / "unwritten.db").resolve().as_posix()


def build_world(database_url: str, seed: int | None = None) -> WorldEngine:
    repository = Repository(database_url)
    repository.create_all()
    content = Node17Content()
    dialogue = TemplateDialogueProvider(content)
    engine = WorldEngine(repository, content, dialogue)
    engine.ensure_initialized(seed=seed)
    return engine


def create_app(database_url: str | None = None) -> FastAPI:
    engine = build_world(database_url or default_database_url())
    app = FastAPI(title="UNWRITTEN", version="0.0.1")
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
