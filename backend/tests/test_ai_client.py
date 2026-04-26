from __future__ import annotations

import pytest

from app import ai_client


class FakeResponse:
    def __init__(self, status_code: int, payload=None, json_error: Exception | None = None):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


def test_post_uses_configured_ai_system_url_and_timeout(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(200, {"ok": True})

    monkeypatch.setenv("AI_SYSTEM_URL", "http://ai-system.local/")
    monkeypatch.setenv("AI_SYSTEM_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setattr(ai_client.requests, "post", fake_post)

    result = ai_client._post("/health-check", {"ping": "pong"})

    assert result == {"ok": True}
    assert calls == [
        {
            "url": "http://ai-system.local/health-check",
            "json": {"ping": "pong"},
            "timeout": 12.5,
        }
    ]


def test_post_raises_clear_error_for_non_json_response(monkeypatch):
    monkeypatch.setattr(
        ai_client.requests,
        "post",
        lambda *_, **__: FakeResponse(502, json_error=ValueError("not json")),
    )

    with pytest.raises(ai_client.AIServiceError, match="non-JSON"):
        ai_client._post("/bad", {})


def test_post_raises_detail_from_error_payload(monkeypatch):
    monkeypatch.setattr(
        ai_client.requests,
        "post",
        lambda *_, **__: FakeResponse(500, {"detail": {"error": "Rate Limited"}}),
    )

    with pytest.raises(ai_client.AIServiceError, match="Rate Limited"):
        ai_client._post("/bad", {})


def test_request_portfolio_review_shapes_payload(monkeypatch):
    captured: dict = {}

    def fake_post(path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {"crew_output": "done"}

    monkeypatch.setattr(ai_client, "_post", fake_post)

    result = ai_client.request_portfolio_review(
        {"id": 7, "name": "Test"},
        [{"symbol": "AAPL", "type": "buy"}],
        mode="full",
    )

    assert result == {"crew_output": "done"}
    assert captured == {
        "path": "/orchestrate/portfolio-review",
        "payload": {
            "portfolio": {"id": 7, "name": "Test"},
            "transactions": [{"symbol": "AAPL", "type": "buy"}],
            "mode": "full",
        },
    }
