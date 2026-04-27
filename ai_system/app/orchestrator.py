"""Thin compatibility wrapper around the compiled LangGraph workflow."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_system.langgraph.graph import graph


def portfolio_review(
    portfolio_payload: dict, transactions_payload: list[dict], mode: str = "quick"
) -> dict:
    result = graph.invoke(
        {
            "request_id": datetime.now(timezone.utc).isoformat(),
            "portfolio": portfolio_payload,
            "transactions": transactions_payload,
            "route": mode,
        }
    )
    return result["response"]


def comprehensive_portfolio_review(
    portfolio_payload: dict, transactions_payload: list[dict]
) -> dict:
    return portfolio_review(portfolio_payload, transactions_payload, "full")
