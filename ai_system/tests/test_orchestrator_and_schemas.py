from __future__ import annotations

from ai_system.langgraph import nodes
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


def test_crew_two_market_summary_uses_structured_output(monkeypatch):
    monkeypatch.setattr(
        nodes.portfolio,
        "analyze_portfolio",
        lambda portfolio: {"analysis": "Portfolio analysis ok."},
    )
    monkeypatch.setattr(nodes, "_emit_llm_thinking", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        nodes.market,
        "analyze_sentiment",
        lambda symbols, detail_level: {
            "structured_output": {
                "summary": "MSFT and NVDA signals are mixed.",
                "severity": "medium",
                "confidence": "high",
                "key_factors": ["Earnings and AI demand are the main driver."],
                "recommended_actions": ["Validate with live prices before trading."],
            }
        },
    )
    state = {
        "portfolio": {
            "id": 1,
            "name": "Demo",
            "assets": [{"symbol": "MSFT"}, {"symbol": "NVDA"}],
        },
        "transactions": [],
        "analysis_trace": [],
    }

    result = nodes.run_full_crew_two(state)

    assert "Market MSFT and NVDA signals are mixed." in result["crew2_output"]
    assert (
        "Signal: severity=medium; confidence=high; "
        "driver=Earnings and AI demand are the main driver."
    ) in result["crew2_output"]
    assert "Action: Validate with live prices before trading." in result["crew2_output"]
    assert "neutral bias" not in result["crew2_output"]


def test_crew_one_uses_compliance_agent(monkeypatch):
    compliance_called: dict = {}

    monkeypatch.setattr(nodes.risk, "score_transaction", lambda txn: {"score": 12})
    monkeypatch.setattr(
        nodes.risk,
        "assess_portfolio_risk",
        lambda portfolio, market_conditions: {"risk_analysis": "Risk analysis ok."},
    )
    monkeypatch.setattr(
        nodes.risk,
        "detect_fraud_risk",
        lambda transactions, portfolio, ml_scores: {"assessment": "Fraud review ok."},
    )
    monkeypatch.setattr(nodes, "_emit_llm_thinking", lambda *args, **kwargs: None)

    def fake_compliance_invoke(portfolio, transactions, mode="quick"):
        compliance_called["portfolio"] = portfolio
        compliance_called["transactions"] = transactions
        compliance_called["mode"] = mode
        return {
            "prechecks": {
                "rule_hits": [
                    {
                        "rule_id": "UNSUPPORTED_TXN_TYPE",
                        "severity": "high",
                        "basis": "internal_schema_control",
                        "description": "Unsupported transaction type found.",
                    }
                ]
            },
            "summary": "Fallback compliance summary.",
            "structured_output": {
                "summary": "Compliance agent reviewed transaction policy checks.",
                "severity": "high",
                "confidence": "medium",
                "key_factors": ["Unsupported transaction type found."],
                "recommended_actions": ["Queue the activity for analyst review."],
            },
        }

    monkeypatch.setattr(nodes.compliance, "invoke", fake_compliance_invoke)
    state = {
        "portfolio": {"id": 1, "name": "Demo"},
        "transactions": [{"symbol": "MSFT", "type": "buy"}],
        "analysis_trace": [],
    }

    result = nodes.run_full_crew_one(state)

    assert compliance_called == {
        "portfolio": {"id": 1, "name": "Demo"},
        "transactions": [{"symbol": "MSFT", "type": "buy"}],
        "mode": "full",
    }
    assert "Compliance 1 compliance precheck(s) require analyst review." in result["crew1_output"]
    assert (
        "Signal: severity=high; confidence=medium; "
        "basis=internal_schema_control; driver=Unsupported transaction type found."
    ) in result["crew1_output"]
    assert "Action: Queue the activity for analyst review." in result["crew1_output"]


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
