"""Search routes with LLM guardrails and LLM-powered knowledge search."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.ai_client import AIServiceError, check_search_guardrail, search_knowledge
from app.api.common import search_analysis_records, search_risk_records

try:
    import vector_store
except Exception:  # pragma: no cover - optional runtime dependency
    vector_store = None


router = APIRouter()


def _run_guardrail(query: str) -> dict[str, Any] | None:
    """
    Returns a blocked-response dict if the query should be rejected, else None.
    Swallows AI service errors so a guardrail outage never blocks legitimate searches.
    """
    try:
        result = check_search_guardrail(query)
        if result.get("blocked"):
            return {
                "blocked": True,
                "reason": result.get("reason", "Query blocked by policy."),
                "results": [],
            }
    except (AIServiceError, Exception):
        pass  # fail open — don't block searches if guardrail is down
    return None


def _llm_search(query: str, context_docs: list[dict]) -> dict[str, Any]:
    """Call the LLM knowledge-search endpoint and return its response."""
    try:
        return search_knowledge(query, context_docs)
    except (AIServiceError, Exception):
        return {}


@router.post("/api/search/analyses")
def search_analyses(
    payload: dict[str, Any] = Body(...),
) -> dict[str, list[dict[str, Any]]]:
    payload = payload or {}
    query = str(payload.get("query") or "").strip()
    portfolio_id = payload.get("portfolio_id")
    if not query:
        raise HTTPException(status_code=400, detail="query required")

    blocked = _run_guardrail(query)
    if blocked:
        return blocked  # type: ignore[return-value]

    # Vector store search
    results: list[dict[str, Any]] = []
    if vector_store is not None:
        try:
            results = vector_store.search_portfolio(query, portfolio_id)
        except Exception:
            pass
    if not results:
        results = search_analysis_records(query, portfolio_id=portfolio_id)

    # LLM-powered answer (runs regardless of vector results)
    llm = _llm_search(query, results)

    return {
        "results": results,
        "agent_response": llm.get("response") or "",
        "context_count": llm.get("context_count", len(results)),
        "timestamp": llm.get("timestamp"),
    }


@router.post("/api/search/risks")
def search_risks(
    payload: dict[str, Any] = Body(...),
) -> dict[str, list[dict[str, Any]]]:
    payload = payload or {}
    query = str(payload.get("query") or "").strip()
    portfolio_id = payload.get("portfolio_id")
    if not query:
        raise HTTPException(status_code=400, detail="query required")

    blocked = _run_guardrail(query)
    if blocked:
        return blocked  # type: ignore[return-value]

    results: list[dict[str, Any]] = []
    if vector_store is not None:
        try:
            results = vector_store.search_risk(query, portfolio_id)
        except Exception:
            pass
    if not results:
        results = search_risk_records(query, portfolio_id=portfolio_id)

    llm = _llm_search(query, results)

    return {
        "results": results,
        "agent_response": llm.get("response") or "",
        "context_count": llm.get("context_count", len(results)),
        "timestamp": llm.get("timestamp"),
    }


@router.post("/api/search/market")
def search_market(
    payload: dict[str, Any] = Body(...),
) -> dict[str, list[dict[str, Any]]]:
    payload = payload or {}
    query = str(payload.get("query") or "").strip()
    symbol = str(payload.get("symbol") or "").strip() or None
    if not query:
        raise HTTPException(status_code=400, detail="query required")

    blocked = _run_guardrail(query)
    if blocked:
        return blocked  # type: ignore[return-value]

    results: list[dict[str, Any]] = []
    if vector_store is not None:
        try:
            results = vector_store.search_market(query, symbol)
        except Exception:
            pass
    if not results:
        results = search_analysis_records(query, symbol=symbol)

    llm = _llm_search(query, results)

    return {
        "results": results,
        "agent_response": llm.get("response") or "",
        "context_count": llm.get("context_count", len(results)),
        "timestamp": llm.get("timestamp"),
    }
