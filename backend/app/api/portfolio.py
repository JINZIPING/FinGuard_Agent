"""Portfolio, asset, alert, and analysis routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.ai_client import (
    AIServiceError,
    request_market_recommendation,
    request_portfolio_review,
    request_transaction_risk,
)
from app.analysis_store import persist_analysis
from app.api.common import (
    build_review_payload,
    fetch_assets,
    fetch_transactions,
    get_portfolio_or_404,
    serialize_alert,
    serialize_asset,
    serialize_transaction,
    utc_now,
)
from app.db import execute, fetch_all, fetch_one
from app.schemas import (
    CreateAlertRequest,
    CreateAssetRequest,
    CreatePortfolioRequest,
    CreateTransactionRequest,
    QuickRecommendationRequest,
    RecommendationRequest,
)
from app.transaction_side_effects import (
    build_transaction_risk_payload,
    create_transaction_with_side_effects,
)

try:
    import vector_store
except Exception:  # pragma: no cover - optional runtime dependency
    vector_store = None


router = APIRouter()


@router.post("/api/portfolio", status_code=201)
@router.post("/api/portfolios", status_code=201)
def create_portfolio(payload: CreatePortfolioRequest | None = None) -> dict[str, Any]:
    payload = payload or CreatePortfolioRequest()
    now = utc_now()
    portfolio_id = execute(
        """
        INSERT INTO portfolios (user_id, name, total_value, cash_balance, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload.user_id or str(uuid.uuid4()),
            payload.name,
            payload.initial_investment,
            payload.initial_investment,
            now,
            now,
        ),
    )
    portfolio = get_portfolio_or_404(portfolio_id)
    return {
        "id": portfolio["id"],
        "user_id": portfolio["user_id"],
        "name": portfolio["name"],
        "created_at": portfolio["created_at"],
    }


@router.get("/api/portfolios")
def list_portfolios() -> dict[str, list[dict[str, Any]]]:
    return {
        "portfolios": fetch_all(
            "SELECT * FROM portfolios ORDER BY created_at DESC, id DESC"
        )
    }


@router.get("/api/portfolio/{portfolio_id}")
@router.get("/api/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: int) -> dict[str, Any]:
    portfolio = get_portfolio_or_404(portfolio_id)
    assets = fetch_assets(portfolio_id)
    return {
        "id": portfolio["id"],
        "user_id": portfolio["user_id"],
        "name": portfolio["name"],
        "total_value": portfolio["total_value"],
        "cash_balance": portfolio["cash_balance"],
        "assets_count": len(assets),
        "created_at": portfolio["created_at"],
        "updated_at": portfolio["updated_at"],
    }


@router.post("/api/portfolio/{portfolio_id}/asset", status_code=201)
def add_asset(
    portfolio_id: int, payload: CreateAssetRequest | None = None
) -> dict[str, Any]:
    payload = payload or CreateAssetRequest()
    get_portfolio_or_404(portfolio_id)
    asset_id = execute(
        """
        INSERT INTO assets (
            portfolio_id, symbol, name, quantity, purchase_price,
            current_price, asset_type, sector, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            portfolio_id,
            payload.symbol.upper(),
            payload.name,
            payload.quantity,
            payload.purchase_price,
            payload.current_price
            if payload.current_price is not None
            else payload.purchase_price,
            payload.asset_type,
            payload.sector,
            utc_now(),
        ),
    )
    asset = fetch_one("SELECT * FROM assets WHERE id = ?", (asset_id,))
    return {
        "id": asset["id"],
        "symbol": asset["symbol"],
        "quantity": asset["quantity"],
        "created_at": asset["created_at"],
    }


@router.get("/api/portfolio/{portfolio_id}/assets")
@router.get("/api/portfolios/{portfolio_id}/assets")
def list_assets(portfolio_id: int) -> dict[str, list[dict[str, Any]]]:
    get_portfolio_or_404(portfolio_id)
    return {"assets": [serialize_asset(asset) for asset in fetch_assets(portfolio_id)]}


@router.post("/api/portfolio/{portfolio_id}/transaction", status_code=201)
@router.post("/api/portfolios/{portfolio_id}/transactions", status_code=201)
def add_transaction(
    portfolio_id: int, payload: CreateTransactionRequest | None = None
) -> dict[str, Any]:
    payload = payload or CreateTransactionRequest()
    portfolio = get_portfolio_or_404(portfolio_id)
    payload_data = payload.model_dump()
    total_amount = payload.quantity * payload.price
    try:
        risk_result = request_transaction_risk(
            build_transaction_risk_payload(payload_data, total_amount=total_amount)
        )
    except AIServiceError:
        risk_result = None

    created = create_transaction_with_side_effects(
        portfolio,
        payload_data,
        risk_result=risk_result,
        now=utc_now(),
    )
    transaction = created["transaction"]
    response = {
        "id": transaction["id"],
        "symbol": transaction["symbol"],
        "type": transaction["transaction_type"],
        "amount": transaction["total_amount"],
        "timestamp": transaction["timestamp"],
    }
    if created.get("risk"):
        response["risk"] = created["risk"]
    return response


@router.get("/api/portfolio/{portfolio_id}/transactions")
@router.get("/api/portfolios/{portfolio_id}/transactions")
def list_transactions(portfolio_id: int) -> dict[str, list[dict[str, Any]]]:
    get_portfolio_or_404(portfolio_id)
    return {
        "transactions": [
            serialize_transaction(txn)
            for txn in fetch_transactions(portfolio_id, limit=100)
        ]
    }


@router.post("/api/portfolio/{portfolio_id}/analyze")
@router.post("/api/portfolios/{portfolio_id}/analyze")
def analyze_portfolio(portfolio_id: int) -> dict[str, Any]:
    review_portfolio, review_transactions = build_review_payload(portfolio_id)
    try:
        result = request_portfolio_review(review_portfolio, review_transactions, "full")
    except (AIServiceError, Exception) as exc:
        msg = str(exc)
        if "rate limit" in msg.lower() or "429" in msg:
            raise HTTPException(status_code=429, detail="AI analysis is temporarily rate-limited. Please try again in 30-60 seconds.") from exc
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {msg[:300]}") from exc
    persist_analysis(
        portfolio_id,
        "full",
        result,
        metadata={"source": "portfolio_analysis", "mode": "full"},
    )
    return result


@router.post("/api/portfolio/{portfolio_id}/quick-recommendation")
@router.post("/api/portfolios/{portfolio_id}/quick-recommendation")
def quick_recommendation(
    portfolio_id: int, payload: QuickRecommendationRequest | None = None
) -> dict[str, Any]:
    payload = payload or QuickRecommendationRequest()
    review_portfolio, review_transactions = build_review_payload(portfolio_id)
    try:
        result = request_portfolio_review(
            review_portfolio, review_transactions, payload.mode
        )
    except (AIServiceError, Exception) as exc:
        msg = str(exc)
        if "rate limit" in msg.lower() or "429" in msg:
            raise HTTPException(status_code=429, detail="AI recommendation is temporarily rate-limited. Please try again in 30-60 seconds.") from exc
        raise HTTPException(status_code=500, detail=f"AI recommendation failed: {msg[:300]}") from exc
    persist_analysis(
        portfolio_id,
        payload.mode,
        result,
        metadata={"source": "portfolio_analysis", "mode": payload.mode},
    )
    return result


@router.post("/api/portfolio/{portfolio_id}/recommendation")
@router.post("/api/portfolios/{portfolio_id}/recommendation")
def get_recommendation(
    portfolio_id: int, payload: RecommendationRequest | None = None
) -> dict[str, Any]:
    payload = payload or RecommendationRequest()
    portfolio = get_portfolio_or_404(portfolio_id)
    symbol = payload.symbol.upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol required")
    try:
        result = request_market_recommendation(
            symbol, float(portfolio["total_value"]), payload.risk_profile
        )
    except (AIServiceError, Exception) as exc:
        msg = str(exc)
        if "rate limit" in msg.lower() or "429" in msg:
            raise HTTPException(status_code=429, detail="AI recommendation is temporarily rate-limited. Please try again in 30-60 seconds.") from exc
        raise HTTPException(status_code=500, detail=f"AI recommendation failed: {msg[:300]}") from exc
    if vector_store is not None:
        try:
            vector_store.store_market_analysis(
                symbol,
                result.get("recommendation", ""),
                extra={
                    "record_type": "recommendation",
                    "portfolio_id": str(portfolio_id),
                },
            )
        except Exception:
            pass
    return result


@router.post("/api/portfolio/{portfolio_id}/alert", status_code=201)
@router.post("/api/portfolios/{portfolio_id}/alert", status_code=201)
def create_alert(
    portfolio_id: int, payload: CreateAlertRequest | None = None
) -> dict[str, Any]:
    payload = payload or CreateAlertRequest()
    get_portfolio_or_404(portfolio_id)
    alert_id = execute(
        """
        INSERT INTO alerts (
            portfolio_id, alert_type, symbol, target_price, threshold,
            message, is_active, triggered, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            portfolio_id,
            payload.alert_type,
            payload.symbol,
            payload.target_price,
            payload.threshold,
            payload.message,
            1,
            0,
            utc_now(),
        ),
    )
    alert = fetch_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    return {
        "id": alert["id"],
        "alert_type": alert["alert_type"],
        "is_active": bool(alert["is_active"]),
        "created_at": alert["created_at"],
    }


@router.get("/api/portfolio/{portfolio_id}/alerts")
@router.get("/api/portfolios/{portfolio_id}/alerts")
def list_alerts(portfolio_id: int) -> dict[str, list[dict[str, Any]]]:
    get_portfolio_or_404(portfolio_id)
    alerts = fetch_all(
        """
        SELECT id, alert_type, symbol, target_price, threshold, message,
               is_active, triggered, created_at
        FROM alerts
        WHERE portfolio_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (portfolio_id,),
    )
    return {"alerts": [serialize_alert(alert) for alert in alerts]}
