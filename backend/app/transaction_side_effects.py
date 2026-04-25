"""Atomic transaction persistence and case side effects."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.analysis_store import persist_analysis, sync_analysis_record, utc_now
from app.db import execute, fetch_one, transaction

try:
    import vector_store
except Exception:  # pragma: no cover - optional runtime dependency
    vector_store = None


logger = logging.getLogger(__name__)

CASE_OPEN_THRESHOLD = 55.0
SLA_HOURS = {"critical": 4, "high": 12, "medium": 48, "low": 120}


def _risk_label(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _priority_from_label(label: str) -> str:
    return {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }.get(label, "medium")


def _sla_due(priority: str, opened_at: datetime) -> str:
    return (opened_at + timedelta(hours=SLA_HOURS.get(priority, 48))).isoformat()


def _risk_flags(risk_result: dict[str, Any] | None) -> list[str]:
    if not risk_result:
        return []
    flags = risk_result.get("flags") or []
    return [str(flag) for flag in flags if str(flag).strip()]


def _risk_score(risk_result: dict[str, Any] | None) -> float:
    if not risk_result:
        return 0.0
    try:
        return float(risk_result.get("risk_score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _case_summary(
    symbol: str, transaction_type: str, risk_result: dict[str, Any]
) -> str:
    score = _risk_score(risk_result)
    label = str(risk_result.get("risk_label") or _risk_label(score))
    flags = _risk_flags(risk_result)
    if flags:
        return (
            f"Transaction {symbol} {transaction_type} scored {score:.1f}/100 "
            f"({label}). Flags: {', '.join(flags)}."
        )
    return f"Transaction {symbol} {transaction_type} scored {score:.1f}/100 ({label})."


def _risk_search_text(
    transaction_row: dict[str, Any], risk_result: dict[str, Any]
) -> str:
    flags = ", ".join(_risk_flags(risk_result)) or "none"
    score = _risk_score(risk_result)
    label = str(risk_result.get("risk_label") or _risk_label(score))
    return (
        f"Transaction risk assessment for {transaction_row['symbol']} "
        f"{transaction_row['transaction_type']} transaction #{transaction_row['id']} "
        f"on portfolio {transaction_row['portfolio_id']}. "
        f"Amount {transaction_row['total_amount']}, score {score:.1f}, "
        f"label {label}, flags {flags}."
    )


def _vector_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
            continue
        cleaned[key] = json.dumps(value, ensure_ascii=True, sort_keys=True)
    return cleaned


def build_transaction_risk_payload(
    payload: dict[str, Any],
    *,
    total_amount: float | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    now = observed_at or datetime.now(timezone.utc)
    amount = float(
        total_amount
        if total_amount is not None
        else float(payload.get("quantity", 0)) * float(payload.get("price", 0))
    )
    return {
        "amount": amount,
        "transaction_type": payload.get("type", "buy"),
        "asset_type": payload.get("asset_type", "stock"),
        "sector": payload.get("sector", "Unknown"),
        "sender_country": payload.get("sender_country", "US"),
        "receiver_country": payload.get("receiver_country", "US"),
        "currency": payload.get("currency", "USD"),
        "channel": payload.get("channel", "web"),
        "device_type": payload.get("device_type", "desktop"),
        "is_new_payee": payload.get("is_new_payee", 0),
        "account_age_days": payload.get("account_age_days", 365),
        "customer_avg_txn_amount": payload.get("customer_avg_txn_amount", amount),
        "customer_txn_count_30d": payload.get("customer_txn_count_30d", 1),
        "amount_deviation_from_avg": payload.get("amount_deviation_from_avg", 0),
        "time_of_day_hour": now.hour,
        "is_weekend": int(now.weekday() >= 5),
        "ip_country_match": payload.get("ip_country_match", 1),
        "failed_login_attempts_24h": payload.get("failed_login_attempts_24h", 0),
        "num_txns_last_1h": payload.get("num_txns_last_1h", 0),
        "num_txns_last_24h": payload.get("num_txns_last_24h", 0),
        "days_since_last_txn": payload.get("days_since_last_txn", 1),
        "receiver_account_age_days": payload.get("receiver_account_age_days", 365),
        "is_high_risk_country": payload.get("is_high_risk_country", 0),
        "is_sanctioned_country": payload.get("is_sanctioned_country", 0),
        "pep_flag": payload.get("pep_flag", 0),
        "portfolio_concentration_pct": payload.get("portfolio_concentration_pct", 10),
        "market_volatility_index": payload.get("market_volatility_index", 20),
    }


def create_transaction_with_side_effects(
    portfolio: dict[str, Any],
    payload: dict[str, Any],
    *,
    risk_result: dict[str, Any] | None = None,
    now: str | None = None,
    tenant_id: int | None = None,
) -> dict[str, Any]:
    created_at = now or utc_now()
    symbol = str(payload.get("symbol", "")).upper()
    transaction_type = str(payload.get("type", "buy"))
    quantity = float(payload.get("quantity", 0))
    price = float(payload.get("price", 0))
    fees = float(payload.get("fees", 0) or 0)
    total_amount = quantity * price
    cash_delta = (
        total_amount + fees if transaction_type == "buy" else -(total_amount - fees)
    )

    alert_row: dict[str, Any] | None = None
    case_row: dict[str, Any] | None = None
    analysis_record: dict[str, Any] | None = None
    transaction_row: dict[str, Any] | None = None
    updated_portfolio: dict[str, Any] | None = None
    persisted_risk = dict(risk_result) if risk_result else None

    with transaction() as conn:
        transaction_id = execute(
            """
            INSERT INTO transactions (
                portfolio_id, symbol, transaction_type, quantity, price,
                total_amount, fees, notes, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                portfolio["id"],
                symbol,
                transaction_type,
                quantity,
                price,
                total_amount,
                fees,
                payload.get("notes"),
                created_at,
            ),
            conn=conn,
        )
        execute(
            "UPDATE portfolios SET cash_balance = ?, updated_at = ? WHERE id = ?",
            (
                float(portfolio["cash_balance"]) - cash_delta,
                created_at,
                portfolio["id"],
            ),
            conn=conn,
        )
        transaction_row = fetch_one(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,), conn=conn
        )
        updated_portfolio = fetch_one(
            "SELECT * FROM portfolios WHERE id = ?", (portfolio["id"],), conn=conn
        )
        if transaction_row is None:
            raise RuntimeError(f"transaction row {transaction_id} missing after insert")

        if persisted_risk is not None:
            analysis_record = persist_analysis(
                int(portfolio["id"]),
                "transaction_risk",
                persisted_risk,
                created_at=created_at,
                metadata={
                    "source": "transaction",
                    "transaction_id": transaction_id,
                    "symbol": symbol,
                    "transaction_type": transaction_type,
                    "risk_score": _risk_score(persisted_risk),
                },
                conn=conn,
                sync_vector=False,
            )

            score = _risk_score(persisted_risk)
            if score >= CASE_OPEN_THRESHOLD:
                flags = _risk_flags(persisted_risk)
                label = str(persisted_risk.get("risk_label") or _risk_label(score))
                priority = _priority_from_label(label)
                opened_at = datetime.fromisoformat(created_at)
                alert_message = (
                    f"ML Risk Alert: Transaction #{transaction_id} scored "
                    f"{score:.1f}/100 ({label}). Flags: {', '.join(flags) or 'none'}"
                )
                alert_id = execute(
                    """
                    INSERT INTO alerts (
                        portfolio_id, alert_type, symbol, message, is_active, triggered, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        portfolio["id"],
                        "ml_risk_detection",
                        symbol,
                        alert_message,
                        1,
                        1,
                        created_at,
                    ),
                    conn=conn,
                )
                alert_row = fetch_one(
                    "SELECT * FROM alerts WHERE id = ?", (alert_id,), conn=conn
                )

                case_id = execute(
                    """
                    INSERT INTO cases (
                        tenant_id, portfolio_id, transaction_id, alert_id, title, subject_user,
                        summary, risk_score, risk_label, priority, symbol, amount, flags, status,
                        source, metadata, state, opened_at, sla_due_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        portfolio["id"],
                        transaction_id,
                        alert_id,
                        f"Review {symbol} {transaction_type} - {label}",
                        portfolio.get("user_id"),
                        _case_summary(symbol, transaction_type, persisted_risk),
                        score,
                        label,
                        priority,
                        symbol,
                        total_amount,
                        json.dumps(flags),
                        "open",
                        "ml_risk_detection",
                        json.dumps(
                            {
                                "transaction_id": transaction_id,
                                "alert_id": alert_id,
                                "risk_result": persisted_risk,
                            },
                            ensure_ascii=True,
                            sort_keys=True,
                        ),
                        "new",
                        opened_at.isoformat(),
                        _sla_due(priority, opened_at),
                        created_at,
                        created_at,
                    ),
                    conn=conn,
                )
                execute(
                    """
                    INSERT INTO case_events (
                        case_id, event_type, body, metadata, timestamp, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case_id,
                        "auto_opened",
                        f"Auto-opened from transaction #{transaction_id} (score={score:.1f}).",
                        json.dumps(
                            {
                                "flags": flags,
                                "risk_score": score,
                                "risk_label": label,
                                "alert_id": alert_id,
                            },
                            ensure_ascii=True,
                            sort_keys=True,
                        ),
                        created_at,
                        created_at,
                    ),
                    conn=conn,
                )
                case_row = fetch_one(
                    "SELECT * FROM cases WHERE id = ?", (case_id,), conn=conn
                )
                persisted_risk["alert_id"] = alert_id
                persisted_risk["case_id"] = case_id

    if analysis_record is not None:
        analysis_record["vector_synced"] = sync_analysis_record(analysis_record)
    if (
        transaction_row is not None
        and persisted_risk is not None
        and vector_store is not None
    ):
        try:
            vector_store.store_risk_assessment(
                str(portfolio["id"]),
                _risk_search_text(transaction_row, persisted_risk),
                risk_score=_risk_score(persisted_risk),
                extra=_vector_metadata(
                    {
                        "transaction_id": transaction_row["id"],
                        "symbol": transaction_row["symbol"],
                        "risk_label": persisted_risk.get("risk_label")
                        or _risk_label(_risk_score(persisted_risk)),
                        "analysis_id": analysis_record["id"]
                        if analysis_record
                        else None,
                        "case_id": persisted_risk.get("case_id"),
                        "alert_id": persisted_risk.get("alert_id"),
                    }
                ),
                doc_id=f"risk_{portfolio['id']}_{transaction_row['id']}",
            )
        except Exception:
            logger.exception(
                "risk vector sync failed for transaction_id=%s", transaction_row["id"]
            )

    return {
        "transaction": transaction_row,
        "portfolio": updated_portfolio,
        "portfolio_id": int(portfolio["id"]),
        "total_amount": total_amount,
        "risk": persisted_risk,
        "risk_analysis": analysis_record,
        "alert": alert_row,
        "case": case_row,
    }
