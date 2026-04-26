from __future__ import annotations

from ai_system.app import orchestrator
from ai_system.app.schemas import PortfolioReviewRequest


def test_portfolio_review_invokes_graph_with_payload_and_mode(monkeypatch):
    captured: dict = {}

    class FakeGraph:
        def invoke(self, state):
            captured["state"] = state
            return {
                "response": {
                    "portfolio_id": state["portfolio"]["id"],
                    "langgraph_route": state["route"],
                    "crew_output": "ok",
                }
            }

    monkeypatch.setattr(orchestrator, "graph", FakeGraph())

    result = orchestrator.portfolio_review(
        {"id": 42, "name": "Demo"},
        [{"symbol": "AAPL", "type": "buy"}],
        mode="full",
    )

    assert result == {
        "portfolio_id": 42,
        "langgraph_route": "full",
        "crew_output": "ok",
    }
    assert captured["state"]["portfolio"] == {"id": 42, "name": "Demo"}
    assert captured["state"]["transactions"] == [{"symbol": "AAPL", "type": "buy"}]
    assert captured["state"]["route"] == "full"
    assert "request_id" in captured["state"]


def test_comprehensive_portfolio_review_uses_full_mode(monkeypatch):
    captured: dict = {}

    def fake_portfolio_review(portfolio_payload, transactions_payload, mode="quick"):
        captured["mode"] = mode
        return {"mode": mode}

    monkeypatch.setattr(orchestrator, "portfolio_review", fake_portfolio_review)

    assert orchestrator.comprehensive_portfolio_review({}, []) == {"mode": "full"}
    assert captured["mode"] == "full"


def test_portfolio_review_request_defaults_and_nested_dump():
    request = PortfolioReviewRequest(
        portfolio={
            "id": 1,
            "name": "Test Portfolio",
            "assets": [{"symbol": "AAPL", "quantity": 2, "current_price": 200}],
        }
    )

    assert request.mode == "quick"
    assert request.transactions == []
    assert request.portfolio.total_value == 0
    assert request.portfolio.assets[0].symbol == "AAPL"
    assert request.portfolio.model_dump()["assets"][0]["current_price"] == 200.0
