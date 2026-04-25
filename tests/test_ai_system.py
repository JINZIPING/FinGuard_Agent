from __future__ import annotations


def test_ai_system_health_reports_mock_mode(ai_system_client):
    response = ai_system_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["response_mode"] == "mock"


def test_quick_portfolio_review_returns_trace(ai_system_client):
    response = ai_system_client.post(
        "/orchestrate/portfolio-review",
        json={
            "portfolio": {
                "id": 1,
                "name": "Quick Demo",
                "total_value": 100000,
                "cash_balance": 12000,
                "assets": [{"symbol": "MSFT", "name": "Microsoft", "quantity": 20}],
            },
            "transactions": [
                {"id": 1, "symbol": "MSFT", "type": "buy", "quantity": 5, "price": 400}
            ],
            "mode": "quick",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_type"] == "quick"
    assert payload["langgraph_route"] == "quick"
    assert len(payload["analysis_trace"]) >= 2
    assert payload["analysis_trace"][0]["node"] == "ingest_request"


def test_full_portfolio_review_returns_all_agent_groups(ai_system_client):
    response = ai_system_client.post(
        "/orchestrate/portfolio-review",
        json={
            "portfolio": {
                "id": 7,
                "name": "Full Demo",
                "total_value": 250000,
                "cash_balance": 35000,
                "assets": [
                    {"symbol": "NVDA", "name": "NVIDIA", "quantity": 20},
                    {"symbol": "MSFT", "name": "Microsoft", "quantity": 24},
                ],
            },
            "transactions": [
                {"id": 1, "symbol": "NVDA", "type": "buy", "quantity": 5, "price": 900},
                {"id": 2, "symbol": "NVDA", "type": "sell", "quantity": 3, "price": 930},
                {"id": 3, "symbol": "MSFT", "type": "buy", "quantity": 2, "price": 415},
                {"id": 4, "symbol": "JPM", "type": "buy", "quantity": 8, "price": 193},
                {"id": 5, "symbol": "GLD", "type": "buy", "quantity": 5, "price": 218},
                {"id": 6, "symbol": "NVDA", "type": "sell", "quantity": 4, "price": 950},
                {"id": 7, "symbol": "MSFT", "type": "buy", "quantity": 1, "price": 420},
                {"id": 8, "symbol": "JPM", "type": "sell", "quantity": 3, "price": 194},
                {"id": 9, "symbol": "GLD", "type": "buy", "quantity": 2, "price": 220},
                {"id": 10, "symbol": "NVDA", "type": "sell", "quantity": 2, "price": 955},
            ],
            "mode": "full",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["langgraph_route"] == "full"
    assert payload["crews_run"] == 3
    assert payload["agents_used"] == 9
    agent_names = {
        entry["name"]
        for entry in payload["analysis_trace"]
        if entry.get("type") == "agent"
    }
    assert "Risk Assessment Agent" in agent_names
    assert "Portfolio Analyst" in agent_names
    assert "Explanation Agent" in agent_names
