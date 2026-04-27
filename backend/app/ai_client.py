"""HTTP client for the ai_system service."""

from __future__ import annotations

import os

import requests


class AIServiceError(RuntimeError):
    """Raised when ai_system returns an unusable response."""


def _post(path: str, payload: dict) -> dict:
    base_url = os.getenv("AI_SYSTEM_URL", "http://localhost:8000").rstrip("/")
    timeout = float(os.getenv("AI_SYSTEM_TIMEOUT_SECONDS", "90"))
    response = requests.post(
        f"{base_url}{path}",
        json=payload,
        timeout=timeout,
    )

    try:
        payload = response.json()
    except ValueError as exc:
        raise AIServiceError("ai_system returned a non-JSON response") from exc

    if response.status_code >= 400:
        detail = (
            payload
            if not isinstance(payload, dict)
            else payload.get("error") or payload.get("detail") or payload
        )
        raise AIServiceError(f"ai_system request failed: {detail}")

    return payload


def request_portfolio_review(
    portfolio: dict, transactions: list[dict], mode: str = "quick"
) -> dict:
    return _post(
        "/orchestrate/portfolio-review",
        {
            "portfolio": portfolio,
            "transactions": transactions,
            "mode": mode,
        },
    )


def request_agent_review(
    agent: str, portfolio: dict, transactions: list[dict], mode: str = "quick"
) -> dict:
    return _post(
        f"/agents/{agent}/invoke",
        {
            "portfolio": portfolio,
            "transactions": transactions,
            "mode": mode,
        },
    )


def request_market_sentiment(symbols: list[str]) -> dict:
    return _post("/market/sentiment", {"symbols": symbols})


def request_market_recommendation(
    symbol: str, portfolio_size: float, risk_profile: str
) -> dict:
    return _post(
        "/market/recommendation",
        {
            "symbol": symbol,
            "portfolio_size": portfolio_size,
            "risk_profile": risk_profile,
        },
    )


def request_transaction_risk(transaction: dict) -> dict:
    return _post("/risk/score-transaction", {"transaction": transaction})


def request_transaction_insights(
    transaction: dict, score: float, factors: dict
) -> dict:
    return _post(
        "/explanation/transaction-insights",
        {
            "transaction": transaction,
            "score": score,
            "factors": factors,
        },
    )
