"""Thin compatibility wrapper around the compiled LangGraph workflow."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_system.langgraph.graph import graph

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover - tracing is optional at import time

    def traceable(*_: object, **__: object) -> object:
        def decorator(func: object) -> object:
            return func

        return decorator


@traceable(name="portfolio_review_orchestration", run_type="chain")
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


@traceable(name="comprehensive_portfolio_review", run_type="chain")
def comprehensive_portfolio_review(
    portfolio_payload: dict, transactions_payload: list[dict]
) -> dict:
    return portfolio_review(portfolio_payload, transactions_payload, "full")
