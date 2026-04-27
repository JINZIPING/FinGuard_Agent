"""Search routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.common import search_analysis_records, search_risk_records

try:
    import vector_store
except Exception:  # pragma: no cover - optional runtime dependency
    vector_store = None


router = APIRouter()


@router.post("/api/search/analyses")
def search_analyses(
    payload: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    payload = payload or {}
    query = str(payload.get("query") or "").strip()
    portfolio_id = payload.get("portfolio_id")
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    if vector_store is not None:
        try:
            return {"results": vector_store.search_portfolio(query, portfolio_id)}
        except Exception:
            pass
    return {"results": search_analysis_records(query, portfolio_id=portfolio_id)}


@router.post("/api/search/risks")
def search_risks(
    payload: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    payload = payload or {}
    query = str(payload.get("query") or "").strip()
    portfolio_id = payload.get("portfolio_id")
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    if vector_store is not None:
        try:
            return {"results": vector_store.search_risk(query, portfolio_id)}
        except Exception:
            pass
    return {"results": search_risk_records(query, portfolio_id=portfolio_id)}


@router.post("/api/search/market")
def search_market(
    payload: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    payload = payload or {}
    query = str(payload.get("query") or "").strip()
    symbol = str(payload.get("symbol") or "").strip() or None
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    if vector_store is not None:
        try:
            return {"results": vector_store.search_market(query, symbol)}
        except Exception:
            pass
    return {"results": search_analysis_records(query, symbol=symbol)}
