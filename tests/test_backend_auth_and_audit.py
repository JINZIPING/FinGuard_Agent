from __future__ import annotations


def _create_case(client, headers):
    portfolio = client.post(
        "/api/portfolios",
        json={"name": "Auth Demo", "initial_investment": 100000, "user_id": "cust-auth"},
    ).json()
    transaction = client.post(
        f"/api/portfolios/{portfolio['id']}/transactions",
        json={
            "symbol": "NVDA",
            "type": "sell",
            "quantity": 12,
            "price": 975,
            "receiver_country": "IR",
            "is_new_payee": 1,
            "failed_login_attempts_24h": 3,
            "num_txns_last_1h": 4,
            "num_txns_last_24h": 9,
            "amount_deviation_from_avg": 8,
            "is_high_risk_country": 1,
            "is_sanctioned_country": 1,
            "portfolio_concentration_pct": 60,
        },
        headers=headers,
    ).json()
    return transaction["risk"]["case_id"]


def test_cases_require_auth_when_enforced(backend_auth):
    response = backend_auth["client"].get("/api/cases")
    assert response.status_code == 401


def test_audit_verification_requires_supervisor(backend_auth):
    client = backend_auth["client"]
    analyst_headers = backend_auth["headers_for"](backend_auth["users"]["analyst"])
    supervisor_headers = backend_auth["headers_for"](backend_auth["users"]["supervisor"])

    case_id = _create_case(client, analyst_headers)
    client.get(f"/api/cases/{case_id}", headers=analyst_headers)

    denied = client.get("/api/audit/verify", headers=analyst_headers)
    assert denied.status_code == 403

    allowed = client.get("/api/audit/verify", headers=supervisor_headers)
    assert allowed.status_code == 200
    assert allowed.json()["ok"] is True


def test_analyst_cannot_assign_case_to_other_user(backend_auth):
    client = backend_auth["client"]
    analyst = backend_auth["users"]["analyst"]
    supervisor = backend_auth["users"]["supervisor"]
    analyst_headers = backend_auth["headers_for"](analyst)

    case_id = _create_case(client, analyst_headers)
    denied = client.post(
        f"/api/cases/{case_id}/assign",
        json={"assignee_id": supervisor["id"]},
        headers=analyst_headers,
    )
    assert denied.status_code == 403


def test_supervisor_can_export_sar_when_auth_enabled(backend_auth):
    client = backend_auth["client"]
    supervisor_headers = backend_auth["headers_for"](backend_auth["users"]["supervisor"])
    case_id = _create_case(client, supervisor_headers)

    sar = client.get(f"/api/sar/{case_id}.json", headers=supervisor_headers)
    assert sar.status_code == 200
    assert sar.json()["filing_metadata"]["case_id"] == case_id
