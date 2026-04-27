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
    try:
        result = check_search_guardrail(query)
        if result.get("blocked"):
            return {
                "blocked": True,
                "reason": result.get("reason", "Query blocked by policy."),
                "results": [],
            }
    except (AIServiceError, Exception):
        pass
    return None


def _llm_search(query: str, context_docs: list[dict]) -> dict[str, Any]:
    """Call the LLM knowledge-search endpoint. Never returns empty — always has agent_response."""
    try:
        result = search_knowledge(query, context_docs)
        # ai_system returns 'agent_response', normalise here
        answer = result.get("agent_response") or result.get("response") or ""
        return {**result, "agent_response": answer}
    except (AIServiceError, Exception):
        pass

    # Fallback: build a basic answer from the context docs themselves
    if context_docs:
        snippets = []
        for doc in context_docs[:5]:
            text = (doc.get("analysis") or doc.get("content") or
                    doc.get("text") or doc.get("document") or "")
            if text:
                snippets.append(str(text)[:300])
        if snippets:
            return {
                "agent_response": "**Based on available records:**\n\n" + "\n\n---\n\n".join(snippets),
                "context_count": len(context_docs),
                "timestamp": None,
            }

    # Last resort: return a helpful message rather than empty
    return {
        "agent_response": (
            f"I searched for **\"{query}\"** but the AI service is currently unavailable. "
            "The vector store and database were queried — please try again in a moment, "
            "or run an AI Analysis first to populate the knowledge base."
        ),
        "context_count": 0,
        "timestamp": None,
    }


@router.post("/api/search/analyses")
def search_analyses(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
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
            results = vector_store.search_portfolio(query, portfolio_id)
        except Exception:
            pass
    if not results:
        results = search_analysis_records(query, portfolio_id=portfolio_id)

    llm = _llm_search(query, results)

    return {
        "results": results,
        "agent_response": llm.get("agent_response") or "",
        "thinking": llm.get("thinking") or "",
        "context_count": llm.get("context_count", len(results)),
        "timestamp": llm.get("timestamp"),
    }


@router.post("/api/search/risks")
def search_risks(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
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
        "agent_response": llm.get("agent_response") or "",
        "thinking": llm.get("thinking") or "",
        "context_count": llm.get("context_count", len(results)),
        "timestamp": llm.get("timestamp"),
    }


@router.post("/api/search/market")
def search_market(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
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
        "agent_response": llm.get("agent_response") or "",
        "thinking": llm.get("thinking") or "",
        "context_count": llm.get("context_count", len(results)),
        "timestamp": llm.get("timestamp"),
    }


@router.post("/api/search/knowledge")
def search_knowledge_base(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """General-purpose LLM knowledge search used by the chatbot."""
    payload = payload or {}
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")

    blocked = _run_guardrail(query)
    if blocked:
        return blocked  # type: ignore[return-value]

    # Pull context from all record types to give the LLM something to work with
    context: list[dict[str, Any]] = []
    context.extend(search_analysis_records(query)[:3])
    context.extend(search_risk_records(query)[:2])

    llm = _llm_search(query, context)
    return {
        "agent_response": llm.get("agent_response") or "",
        "thinking": llm.get("thinking") or "",
        "context_count": llm.get("context_count", len(context)),
        "timestamp": llm.get("timestamp"),
    }
