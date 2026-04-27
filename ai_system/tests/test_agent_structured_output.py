from __future__ import annotations


def test_ai_system_health_reports_mock_mode(ai_system_client):
    response = ai_system_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["response_mode"] == "mock"


def test_transaction_insights_include_structured_output(ai_system_client):
    response = ai_system_client.post(
        "/explanation/transaction-insights",
        json={
            "transaction": {
                "id": 42,
                "symbol": "MSFT",
                "type": "buy",
                "quantity": 10,
                "price": 420,
            },
            "score": 82,
            "factors": {
                "amount": "larger than typical",
                "velocity": "multiple recent transactions",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["insights"]
    assert payload["structured_output"]["summary"]
    assert payload["structured_output"]["recommended_actions"]


def test_portfolio_agent_invoke_includes_metrics_and_structured_output(ai_system_client):
    response = ai_system_client.post(
        "/agents/portfolio/invoke",
        json={
            "portfolio": {
                "id": 9,
                "name": "Portfolio Agent Demo",
                "total_value": 50000,
                "cash_balance": 2500,
                "assets": [{"symbol": "MSFT", "name": "Microsoft", "quantity": 10}],
            },
            "transactions": [
                {"id": 1, "symbol": "MSFT", "type": "buy", "quantity": 2, "price": 400}
            ],
            "mode": "quick",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"] == "portfolio"
    assert payload["metrics"]["asset_count"] == 1
    assert payload["structured_output"]["summary"]
    assert payload["structured_output"]["recommended_actions"]


def test_compliance_agent_invoke_includes_prechecks_and_structured_output(
    ai_system_client,
):
    response = ai_system_client.post(
        "/agents/compliance/invoke",
        json={
            "portfolio": {
                "id": 12,
                "name": "Compliance Demo",
                "total_value": 75000,
                "cash_balance": 10000,
                "assets": [],
            },
            "transactions": [
                {
                    "id": 1,
                    "symbol": "MSFT",
                    "type": "wire",
                    "quantity": 1,
                    "price": 15000,
                }
            ],
            "mode": "quick",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"] == "compliance"
    assert "wire" in payload["prechecks"]["unsupported_types"]
    assert payload["structured_output"]["severity"] == "high"
    assert payload["structured_output"]["recommended_actions"]


def test_market_sentiment_includes_data_basis_and_structured_output(ai_system_client):
    response = ai_system_client.post(
        "/market/sentiment",
        json={"symbols": ["MSFT", "NVDA"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbols"] == ["MSFT", "NVDA"]
    assert payload["data_basis"]["live_market_data"] is False
    assert payload["structured_output"]["summary"]
    assert payload["structured_output"]["recommended_actions"]


def test_market_recommendation_includes_data_basis_and_structured_output(ai_system_client):
    response = ai_system_client.post(
        "/market/recommendation",
        json={
            "symbol": "msft",
            "portfolio_size": 100000,
            "risk_profile": "moderate",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "MSFT"
    assert payload["data_basis"]["live_market_data"] is False
    assert payload["structured_output"]["summary"]
    assert payload["structured_output"]["recommended_actions"]


def test_alert_intake_process_alert_includes_prechecks_and_structured_output():
    from ai_system.app.agents import alert_intake_agent

    payload = alert_intake_agent.process_alert(
        "account",
        {
            "id": "alert-1",
            "timestamp": "2026-04-26T00:00:00Z",
            "amount": 15000,
            "message": "Large account movement detected",
        },
    )
    assert payload["agent"] == "AlertIntake"
    assert payload["prechecks"]["large_amount"] is True
    assert payload["structured_output"]["severity"] == "high"
    assert payload["structured_output"]["recommended_actions"]


def test_alert_intake_validation_uses_missing_field_prechecks():
    from ai_system.app.agents import alert_intake_agent

    payload = alert_intake_agent.validate_alert_integrity(
        {"id": "alert-2", "message": "Missing timestamp"}
    )
    assert payload["agent"] == "AlertIntake"
    assert payload["is_valid"] is False
    assert "timestamp" in payload["prechecks"]["missing_fields"]
    assert payload["structured_output"]["recommended_actions"]


def test_customer_context_profile_includes_prechecks_and_structured_output():
    from ai_system.app.agents import customer_context_agent

    payload = customer_context_agent.build_customer_profile(
        "customer-1",
        {
            "risk_profile": "high risk",
            "investment_goals": "capital preservation",
            "portfolio_value": 250000,
            "segment": "premium",
        },
    )
    assert payload["agent"] == "CustomerContext"
    assert payload["prechecks"]["profile_richness"] == "high"
    assert payload["structured_output"]["severity"] == "high"
    assert payload["structured_output"]["recommended_actions"]


def test_escalation_evaluation_includes_prechecks_and_structured_output():
    from ai_system.app.agents import escalation_case_summary_agent

    payload = escalation_case_summary_agent.evaluate_escalation_need(
        {"id": "case-1", "risk_score": 88, "description": "AML urgent review"},
        {"urgency": "immediate", "regulatory": "SAR review may be required"},
    )
    assert payload["agent"] == "EscalationCaseSummary"
    assert payload["needs_escalation"] is True
    assert payload["prechecks"]["risk_score"] == 88
    assert payload["structured_output"]["severity"] == "critical"
    assert payload["structured_output"]["recommended_actions"]
