from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
from uuid import uuid4
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _purge_modules(prefixes: tuple[str, ...]) -> None:
    for name in list(sys.modules):
        if name in prefixes or name.startswith(tuple(f"{prefix}." for prefix in prefixes)):
            sys.modules.pop(name, None)


@pytest.fixture
def tmp_path() -> Path:
    base_dir = BACKEND_ROOT / "data" / ".tmp-tests"
    base_dir.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base_dir))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def db_file() -> Path:
    base_dir = BACKEND_ROOT / "data"
    base_dir.mkdir(exist_ok=True)
    path = base_dir / f"test_{uuid4().hex}.db"
    try:
        yield path
    finally:
        if path.exists():
            path.unlink()


@pytest.fixture
def ai_system_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AI_RESPONSE_MODE", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _purge_modules(("ai_system",))
    ai_main = importlib.import_module("ai_system.app.main")
    importlib.reload(ai_main)
    with TestClient(ai_main.app) as client:
        yield client


def _build_backend_client(
    *,
    monkeypatch: pytest.MonkeyPatch,
    db_file: Path,
    ai_system_client: TestClient,
    auth_enforced: bool,
):
    monkeypatch.setenv("BACKEND_DB_PATH", str(db_file))
    monkeypatch.setenv("AUTH_ENFORCED", "true" if auth_enforced else "false")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    _purge_modules(("app",))
    main = importlib.import_module("app.main")
    ai_client = importlib.import_module("app.ai_client")
    auth = importlib.import_module("app.auth")
    db = importlib.import_module("app.db")

    def bridge(path: str, payload: dict) -> dict:
        response = ai_system_client.post(path, json=payload)
        try:
            data = response.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise ai_client.AIServiceError("ai_system bridge returned non-JSON") from exc
        if response.status_code >= 400:
            detail = (
                data
                if not isinstance(data, dict)
                else data.get("error") or data.get("detail") or data
            )
            raise ai_client.AIServiceError(f"ai_system request failed: {detail}")
        return data

    monkeypatch.setattr(ai_client, "_post", bridge)
    db.init_db()
    main.app.router.on_startup.clear()
    return main, auth


@pytest.fixture
def backend_client(
    monkeypatch: pytest.MonkeyPatch,
    db_file: Path,
    ai_system_client: TestClient,
):
    main, _ = _build_backend_client(
        monkeypatch=monkeypatch,
        db_file=db_file,
        ai_system_client=ai_system_client,
        auth_enforced=False,
    )
    with TestClient(main.app) as client:
        yield client


@pytest.fixture
def backend_auth(
    monkeypatch: pytest.MonkeyPatch,
    db_file: Path,
    ai_system_client: TestClient,
):
    main, auth = _build_backend_client(
        monkeypatch=monkeypatch,
        db_file=db_file,
        ai_system_client=ai_system_client,
        auth_enforced=True,
    )
    with TestClient(main.app) as client:
        admin = auth.register_user(
            email="admin@test.local",
            password="FinGuard123!",
            name="Admin",
            role="admin",
            tenant_slug=auth.DEFAULT_TENANT_SLUG,
            tenant_name="Default",
        )
        supervisor = auth.register_user(
            email="supervisor@test.local",
            password="FinGuard123!",
            name="Supervisor",
            role="supervisor",
            tenant_slug=auth.DEFAULT_TENANT_SLUG,
        )
        analyst = auth.register_user(
            email="analyst@test.local",
            password="FinGuard123!",
            name="Analyst",
            role="analyst",
            tenant_slug=auth.DEFAULT_TENANT_SLUG,
        )

        def headers_for(user: dict) -> dict[str, str]:
            return {"Authorization": f"Bearer {auth.issue_token(user)}"}

        yield {
            "client": client,
            "auth": auth,
            "users": {
                "admin": admin,
                "supervisor": supervisor,
                "analyst": analyst,
            },
            "headers_for": headers_for,
        }
