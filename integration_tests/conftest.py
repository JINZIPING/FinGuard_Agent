from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class _RequestsCompatResponse:
    def __init__(self, status_code: int, payload: object):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def ai_system_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AI_RESPONSE_MODE", "mock")
    from ai_system.app.main import app as ai_system_app

    with TestClient(ai_system_app) as client:
        yield client


@pytest.fixture
def backend_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ai_system_client: TestClient,
) -> TestClient:
    if find_spec("jwt") is None:
        pytest.skip("Integration tests require backend dependencies (missing PyJWT).")

    monkeypatch.setenv("AI_RESPONSE_MODE", "mock")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("BACKEND_DB_PATH", str(tmp_path / "integration.db"))
    monkeypatch.setenv("AI_SYSTEM_URL", "http://ai-system.local")
    monkeypatch.setenv("AI_SYSTEM_TIMEOUT_SECONDS", "30")

    from app import ai_client as backend_ai_client
    from app.main import app as backend_app

    def _bridge_post(url: str, json: dict, timeout: float):
        _ = timeout
        path = urlparse(url).path
        response = ai_system_client.post(path, json=json)
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": response.text}
        return _RequestsCompatResponse(response.status_code, payload)

    monkeypatch.setattr(backend_ai_client.requests, "post", _bridge_post)

    with TestClient(backend_app) as client:
        yield client
