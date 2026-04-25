from __future__ import annotations

from scripts.seed_demo_data import seed_demo_data


def test_seed_script_creates_demo_case(monkeypatch, db_file):
    monkeypatch.setenv("BACKEND_DB_PATH", str(db_file))
    summary = seed_demo_data(reset=True)
    assert summary["portfolio"]["id"] > 0
    assert summary["case"]["id"] > 0
    assert summary["case"]["state"] == "new"


def test_portfolio_analysis_flow_returns_trace(backend_client):
    create = backend_client.post(
        "/api/portfolios",
        json={"name": "Trace Demo", "initial_investment": 125000, "user_id": "cust-1"},
    )
    portfolio_id = create.json()["id"]

    backend_client.post(
        f"/api/portfolio/{portfolio_id}/asset",
        json={
            "symbol": "NVDA",
            "name": "NVIDIA",
            "quantity": 12,
            "purchase_price": 890,
            "current_price": 930,
            "asset_type": "stock",
            "sector": "Technology",
        },
    )
    backend_client.post(
        f"/api/portfolio/{portfolio_id}/transaction",
        json={"symbol": "NVDA", "type": "buy", "quantity": 4, "price": 910, "fees": 5},
    )

    response = backend_client.post(f"/api/portfolios/{portfolio_id}/analyze")
    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolio_id"] == portfolio_id
    assert payload["analysis_trace"]
    assert payload["langgraph_route"] in {"quick", "full"}


def test_suspicious_transaction_opens_case_and_exports_sar(backend_client):
    create = backend_client.post(
        "/api/portfolios",
        json={"name": "Compliance Demo", "initial_investment": 300000, "user_id": "cust-2"},
    )
    portfolio_id = create.json()["id"]

    response = backend_client.post(
        f"/api/portfolios/{portfolio_id}/transactions",
        json={
            "symbol": "NVDA",
            "type": "sell",
            "quantity": 18,
            "price": 980,
            "fees": 15,
            "notes": "Suspicious demo transaction",
            "receiver_country": "IR",
            "is_new_payee": 1,
            "failed_login_attempts_24h": 5,
            "num_txns_last_1h": 7,
            "num_txns_last_24h": 12,
            "amount_deviation_from_avg": 11,
            "is_high_risk_country": 1,
            "is_sanctioned_country": 1,
            "portfolio_concentration_pct": 75,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["risk"]["case_id"] > 0

    case_list = backend_client.get("/api/cases?per_page=20")
    assert case_list.status_code == 200
    items = case_list.json()["items"]
    case = next(item for item in items if item["id"] == payload["risk"]["case_id"])
    assert case["state"] == "new"

    sar_json = backend_client.get(f"/api/sar/{case['id']}.json")
    assert sar_json.status_code == 200
    assert sar_json.json()["filing_metadata"]["case_id"] == case["id"]
