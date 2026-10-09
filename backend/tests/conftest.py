from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import build_world, create_app
from app.engine.world import WorldEngine


def open_world(path: Path, seed: int | None = None) -> WorldEngine:
    url = "sqlite:///" + path.resolve().as_posix()
    return build_world(url, seed=seed)


@pytest.fixture
def world(tmp_path: Path):
    engine = open_world(tmp_path / "game.db")
    try:
        yield engine
    finally:
        engine.close()


@pytest.fixture
def client(tmp_path: Path):
    url = "sqlite:///" + (tmp_path / "api.db").resolve().as_posix()
    app = create_app(url)
    with TestClient(app) as test_client:
        yield test_client
    app.state.world.close()
