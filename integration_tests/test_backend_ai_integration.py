from __future__ import annotations


def test_portfolio_analysis_round_trip_through_ai_system(backend_client):
    create_portfolio = backend_client.post(
        "/api/portfolio",
        json={"name": "Integration Portfolio", "initial_investment": 100000},
    )
    assert create_portfolio.status_code == 201
    portfolio_id = create_portfolio.json()["id"]

    add_asset = backend_client.post(
        f"/api/portfolio/{portfolio_id}/asset",
        json={
            "symbol": "MSFT",
            "name": "Microsoft",
            "quantity": 10,
            "purchase_price": 400,
            "current_price": 420,
            "asset_type": "stock",
            "sector": "Technology",
        },
    )
    assert add_asset.status_code == 201

    add_transaction = backend_client.post(
        f"/api/portfolio/{portfolio_id}/transaction",
        json={
            "symbol": "MSFT",
            "type": "buy",
            "quantity": 5,
            "price": 420,
            "asset_type": "stock",
            "sector": "Technology",
            "currency": "USD",
            "channel": "web",
        },
    )
    assert add_transaction.status_code == 201
    transaction_payload = add_transaction.json()
    assert "risk" in transaction_payload
    assert "risk_score" in transaction_payload["risk"]

    analyze = backend_client.post(f"/api/portfolio/{portfolio_id}/analyze")
    assert analyze.status_code == 200
    analysis_payload = analyze.json()
    assert analysis_payload["portfolio_id"] == portfolio_id
    assert analysis_payload["langgraph_route"] == "full"
    assert analysis_payload["crew_output"]

    search = backend_client.post(
        "/api/search/analyses",
        json={"query": "portfolio", "portfolio_id": portfolio_id},
    )
    assert search.status_code == 200
    search_payload = search.json()
    assert search_payload["results"]
    assert any(item["analysis_type"] == "full" for item in search_payload["results"])


def test_market_sentiment_proxy_integration(backend_client):
    response = backend_client.get("/api/sentiment/MSFT")
    assert response.status_code == 200

    payload = response.json()
    assert payload["symbols"] == ["MSFT"]
    assert "sentiment_analysis" in payload
    assert "structured_output" in payload


def test_search_guardrail_blocked_query_flows_through_backend(backend_client):
    response = backend_client.post(
        "/api/search/market",
        json={"query": "drop table users", "symbol": "MSFT"},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["blocked"] is True
    assert payload["results"] == []
    assert "disallowed" in payload["reason"].lower()
