"""Legacy-compatible case workflow routes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from app.ai_client import AIServiceError, request_agent_review, request_portfolio_review
from app.audit import record as record_audit
from app.auth import ROLE_RANK, current_tenant_id, current_user, require_auth
from app.db import execute, fetch_all, fetch_one


router = APIRouter()

CASE_STATES = (
    "new",
    "under_review",
    "escalated",
    "closed_cleared",
    "closed_sar_filed",
    "closed_false_positive",
)
CASE_TRANSITIONS = {
    "new": {"under_review", "closed_false_positive", "closed_cleared"},
    "under_review": {
        "escalated",
        "closed_cleared",
        "closed_sar_filed",
        "closed_false_positive",
    },
    "escalated": {"closed_sar_filed", "closed_cleared", "closed_false_positive"},
    "closed_cleared": set(),
    "closed_sar_filed": set(),
    "closed_false_positive": set(),
}
TERMINAL_STATES = {"closed_cleared", "closed_sar_filed", "closed_false_positive"}
ANALYST_ALLOWED = {
    ("new", "under_review"),
    ("new", "closed_false_positive"),
    ("new", "closed_cleared"),
    ("under_review", "closed_cleared"),
    ("under_review", "closed_false_positive"),
}
SLA_HOURS = {"critical": 4, "high": 12, "medium": 48, "low": 120}


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


def _risk_label(score: int) -> str:
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


def _case_from_row(row: dict[str, Any], include_events: bool = False) -> dict[str, Any]:
    case = {
        "id": row["id"],
        "tenant_id": row.get("tenant_id"),
        "portfolio_id": row.get("portfolio_id"),
        "transaction_id": row.get("transaction_id"),
        "alert_id": row.get("alert_id"),
        "title": row.get("title"),
        "subject_user": row.get("subject_user"),
        "symbol": row.get("symbol"),
        "amount": row.get("amount"),
        "risk_score": row.get("risk_score"),
        "risk_label": row.get("risk_label"),
        "flags": json.loads(row.get("flags") or "[]"),
        "state": row.get("state") or row.get("status"),
        "priority": row.get("priority"),
        "assignee_id": row.get("assignee_id"),
        "opened_at": row.get("opened_at"),
        "closed_at": row.get("closed_at"),
        "sla_due_at": row.get("sla_due_at"),
        "notes": row.get("notes"),
    }
    if include_events:
        event_rows = fetch_all(
            """
            SELECT id, event_type, actor_user_id, actor_email, from_state, to_state, body, data, timestamp
            FROM case_events
            WHERE case_id = ?
            ORDER BY COALESCE(timestamp, created_at) ASC, id ASC
            """,
            (row["id"],),
        )
        case["events"] = [
            {
                "id": event["id"],
                "event_type": event["event_type"],
                "actor_user_id": event.get("actor_user_id"),
                "actor_email": event.get("actor_email"),
                "from_state": event.get("from_state"),
                "to_state": event.get("to_state"),
                "body": event.get("body"),
                "data": json.loads(event.get("data") or "{}"),
                "timestamp": event.get("timestamp"),
            }
            for event in event_rows
        ]
        case["ai_analysis"] = row.get("ai_analysis")
    return case


def _tenant_case_or_404(request: Request, case_id: int) -> dict[str, Any]:
    tenant_id = current_tenant_id(request)
    row = fetch_one(
        """
        SELECT *
        FROM cases
        WHERE id = ? AND tenant_id = ?
        """,
        (case_id, tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return row


def _append_event(
    case_id: int,
    event_type: str,
    *,
    request: Request,
    body: str | None = None,
    data: dict[str, Any] | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
) -> None:
    user = current_user(request)
    execute(
        """
        INSERT INTO case_events (
            case_id, event_type, actor_user_id, actor_email,
            from_state, to_state, body, data, timestamp, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            event_type,
            user["id"] if user else None,
            user["email"] if user else None,
            from_state,
            to_state,
            body,
            json.dumps(data or {}),
            _utc_now(),
            _utc_now(),
        ),
    )


def _portfolio_dict(case: dict[str, Any]) -> dict[str, Any]:
    if not case.get("portfolio_id"):
        return {}
    portfolio = fetch_one(
        "SELECT * FROM portfolios WHERE id = ?", (case["portfolio_id"],)
    )
    if portfolio is None:
        return {}
    assets = fetch_all(
        """
        SELECT symbol, name, quantity, current_price, purchase_price, asset_type
        FROM assets
        WHERE portfolio_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 25
        """,
        (case["portfolio_id"],),
    )
    return {
        "id": portfolio["id"],
        "user_id": portfolio["user_id"],
        "name": portfolio["name"],
        "total_value": portfolio["total_value"],
        "cash_balance": portfolio["cash_balance"],
        "assets": assets,
    }


def _transactions_for_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    if case.get("portfolio_id"):
        return fetch_all(
            """
            SELECT id, symbol, transaction_type AS type, quantity, price, total_amount AS amount, fees, timestamp
            FROM transactions
            WHERE portfolio_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 20
            """,
            (case["portfolio_id"],),
        )
    if case.get("transaction_id"):
        transaction = fetch_one(
            """
            SELECT id, symbol, transaction_type AS type, quantity, price, total_amount AS amount, fees, timestamp
            FROM transactions
            WHERE id = ?
            """,
            (case["transaction_id"],),
        )
        return [transaction] if transaction else []
    return []


def _analysis_body(result: dict[str, Any]) -> str:
    for key in (
        "assessment",
        "analysis",
        "recommendation",
        "crew_output",
        "summary",
        "output",
    ):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    findings = result.get("findings")
    if isinstance(findings, list) and findings:
        return "\n".join(str(item) for item in findings)
    return json.dumps(result, indent=2)


@router.get("/api/cases")
def list_cases(
    request: Request,
    state: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    q: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    require_auth(request)
    tenant_id = current_tenant_id(request)
    query = "SELECT * FROM cases WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if state:
        if state == "open":
            placeholders = ",".join("?" for _ in TERMINAL_STATES)
            query += f" AND COALESCE(state, status) NOT IN ({placeholders})"
            params.extend(sorted(TERMINAL_STATES))
        else:
            query += " AND COALESCE(state, status) = ?"
            params.append(state)
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    if assignee == "me":
        user = current_user(request)
        query += " AND assignee_id = ?"
        params.append(user["id"] if user else -1)
    elif assignee == "unassigned":
        query += " AND assignee_id IS NULL"
    elif assignee and assignee.isdigit():
        query += " AND assignee_id = ?"
        params.append(int(assignee))
    if q:
        query += " AND (title LIKE ? OR subject_user LIKE ? OR symbol LIKE ?)"
        pattern = f"%{q}%"
        params.extend([pattern, pattern, pattern])

    total_row = fetch_one(f"SELECT COUNT(*) AS count FROM ({query})", tuple(params))
    total = int(total_row["count"]) if total_row else 0
    offset = (max(page, 1) - 1) * min(max(per_page, 1), 200)
    query += " ORDER BY COALESCE(opened_at, created_at) DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([min(max(per_page, 1), 200), offset])
    rows = fetch_all(query, tuple(params))
    return {
        "page": max(page, 1),
        "per_page": min(max(per_page, 1), 200),
        "total": total,
        "items": [_case_from_row(row) for row in rows],
    }


@router.get("/api/cases/{case_id}")
def get_case(case_id: int, request: Request) -> dict[str, Any]:
    require_auth(request)
    return _case_from_row(_tenant_case_or_404(request, case_id), include_events=True)


@router.post("/api/cases", status_code=201)
def create_case(
    request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    require_auth(request)
    payload = payload or {}
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    priority = str(payload.get("priority") or "medium").lower()
    if priority not in SLA_HOURS:
        raise HTTPException(
            status_code=400, detail=f"priority must be one of {list(SLA_HOURS)}"
        )

    opened = datetime.utcnow()
    risk_score = int(payload.get("risk_score") or 0)
    case_id = execute(
        """
        INSERT INTO cases (
            tenant_id, portfolio_id, transaction_id, alert_id, title, subject_user,
            symbol, amount, risk_score, risk_label, flags, state, priority,
            opened_at, sla_due_at, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_tenant_id(request),
            payload.get("portfolio_id"),
            payload.get("transaction_id"),
            payload.get("alert_id"),
            title,
            payload.get("subject_user"),
            str(payload.get("symbol") or "").upper() or None,
            payload.get("amount"),
            risk_score,
            payload.get("risk_label") or _risk_label(risk_score),
            json.dumps(payload.get("flags") or []),
            "new",
            priority,
            opened.isoformat(),
            _sla_due(priority, opened),
            payload.get("notes"),
            opened.isoformat(),
            opened.isoformat(),
        ),
    )
    _append_event(
        case_id,
        "opened",
        request=request,
        body=f"Manually opened by {current_user(request)['email']}.",
        to_state="new",
    )
    record_audit(
        "case.opened",
        request=request,
        resource="case",
        resource_id=str(case_id),
        details={"auto": False, "title": title, "priority": priority},
    )
    return _case_from_row(_tenant_case_or_404(request, case_id))


@router.post("/api/cases/{case_id}/assign")
def assign_case(
    case_id: int, request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    user = require_auth(request)
    case = _tenant_case_or_404(request, case_id)
    if (case.get("state") or case.get("status")) in TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="Cannot assign a closed case")
    payload = payload or {}
    assignee_id = payload.get("assignee_id")
    if assignee_id in (None, "", "me"):
        assignee_id = user["id"]
    else:
        try:
            assignee_id = int(assignee_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="assignee_id must be an integer or 'me'"
            ) from exc

    if (
        ROLE_RANK.get(str(user["role"]), 0) < ROLE_RANK["supervisor"]
        and assignee_id != user["id"]
    ):
        raise HTTPException(
            status_code=403, detail="Analysts can only assign cases to themselves"
        )

    assignee = fetch_one(
        "SELECT * FROM users WHERE id = ? AND tenant_id = ?",
        (assignee_id, case["tenant_id"]),
    )
    if assignee is None:
        raise HTTPException(status_code=404, detail="Assignee not found in this tenant")

    execute(
        "UPDATE cases SET assignee_id = ?, updated_at = ? WHERE id = ?",
        (assignee_id, _utc_now(), case_id),
    )
    _append_event(
        case_id,
        "assignment",
        request=request,
        body=f"Assigned to {assignee['email']}.",
        data={
            "from_assignee_id": case.get("assignee_id"),
            "to_assignee_id": assignee_id,
        },
    )
    record_audit(
        "case.assigned",
        request=request,
        resource="case",
        resource_id=str(case_id),
        details={"from": case.get("assignee_id"), "to": assignee_id},
    )
    return _case_from_row(_tenant_case_or_404(request, case_id))


@router.post("/api/cases/{case_id}/notes", status_code=201)
def add_note(
    case_id: int, request: Request, payload: dict[str, Any] | None = None
) -> dict[str, bool]:
    require_auth(request)
    _tenant_case_or_404(request, case_id)
    payload = payload or {}
    body = str(payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="body is required")
    _append_event(case_id, "note", request=request, body=body)
    record_audit(
        "case.note_added",
        request=request,
        resource="case",
        resource_id=str(case_id),
        details={"length": len(body)},
    )
    return {"ok": True}


@router.post("/api/cases/{case_id}/transition")
def transition_case(
    case_id: int, request: Request, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    user = require_auth(request)
    case = _tenant_case_or_404(request, case_id)
    current_state = case.get("state") or case.get("status") or "new"
    if current_state in TERMINAL_STATES:
        raise HTTPException(
            status_code=409, detail="Case is closed — no further transitions"
        )

    payload = payload or {}
    to_state = str(payload.get("to_state") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if to_state not in CASE_STATES:
        raise HTTPException(
            status_code=400, detail=f"to_state must be one of {CASE_STATES}"
        )
    allowed = CASE_TRANSITIONS.get(current_state, set())
    if to_state not in allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Illegal state transition",
                "from_state": current_state,
                "to_state": to_state,
                "allowed": sorted(allowed),
            },
        )
    if (current_state, to_state) not in ANALYST_ALLOWED and ROLE_RANK.get(
        str(user["role"]), 0
    ) < ROLE_RANK["supervisor"]:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "This transition requires supervisor role",
                "from_state": current_state,
                "to_state": to_state,
            },
        )

    closed_at = _utc_now() if to_state in TERMINAL_STATES else None
    execute(
        """
        UPDATE cases
        SET state = ?, status = ?, closed_at = COALESCE(?, closed_at), updated_at = ?
        WHERE id = ?
        """,
        (to_state, to_state, closed_at, _utc_now(), case_id),
    )
    _append_event(
        case_id,
        "state_change",
        request=request,
        body=reason or None,
        from_state=current_state,
        to_state=to_state,
    )
    record_audit(
        "case.state_changed",
        request=request,
        resource="case",
        resource_id=str(case_id),
        details={"from": current_state, "to": to_state, "reason": reason},
    )
    return _case_from_row(_tenant_case_or_404(request, case_id))


@router.post("/api/cases/{case_id}/analyze")
def analyze_case(
    case_id: int, request: Request, payload: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    require_auth(request)
    case = _tenant_case_or_404(request, case_id)
    current_state = case.get("state") or case.get("status") or "new"
    if current_state in TERMINAL_STATES:
        raise HTTPException(
            status_code=409, detail="Case is closed — re-run analysis before closing"
        )

    payload = payload or {}
    action = str(payload.get("action") or "").strip().lower()
    allowed = {"risk", "compliance", "portfolio", "recommendation"}
    if action not in allowed:
        raise HTTPException(
            status_code=400,
            detail={"error": "Unknown action", "allowed": sorted(allowed)},
        )

    portfolio_payload = _portfolio_dict(case)
    transactions_payload = _transactions_for_case(case)

    try:
        if action == "risk":
            result = request_agent_review(
                "risk", portfolio_payload, transactions_payload, "full"
            )
            label = "Risk reassessment"
        elif action == "compliance":
            result = request_agent_review(
                "compliance", portfolio_payload, transactions_payload, "full"
            )
            label = "Compliance review"
        elif action == "portfolio":
            result = request_agent_review(
                "portfolio", portfolio_payload, transactions_payload, "full"
            )
            label = "Portfolio review"
        else:
            result = request_portfolio_review(
                portfolio_payload, transactions_payload, "quick"
            )
            label = "Lightweight recommendation"
    except AIServiceError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "Analysis failed", "detail": str(exc), "action": action},
        ) from exc

    body_text = _analysis_body(result)
    stamp = _utc_now() + "Z"
    execute(
        """
        UPDATE cases
        SET ai_analysis = TRIM(COALESCE(ai_analysis, '') || ? || ?),
            updated_at = ?
        WHERE id = ?
        """,
        (f"\n\n── {label} · {stamp} ──\n", body_text, _utc_now(), case_id),
    )
    _append_event(
        case_id,
        "ai_analysis",
        request=request,
        body=f"{label}\n\n{body_text}".strip(),
        data={"action": action, "raw": result},
    )
    record_audit(
        "case.analyzed",
        request=request,
        resource="case",
        resource_id=str(case_id),
        details={"action": action, "length": len(body_text)},
    )
    event = fetch_one(
        "SELECT id FROM case_events WHERE case_id = ? ORDER BY id DESC LIMIT 1",
        (case_id,),
    )
    return {
        "event_id": event["id"] if event else None,
        "action": action,
        "label": label,
        "body": body_text,
    }


@router.get("/api/cases/{case_id}/customer-360")
def customer_360(case_id: int, request: Request) -> dict[str, Any]:
    require_auth(request)
    case = _tenant_case_or_404(request, case_id)

    query = "SELECT * FROM cases WHERE tenant_id = ? AND id != ?"
    params: list[Any] = [case["tenant_id"], case_id]
    if case.get("subject_user"):
        query += " AND subject_user = ?"
        params.append(case["subject_user"])
    elif case.get("portfolio_id"):
        query += " AND portfolio_id = ?"
        params.append(case["portfolio_id"])
    else:
        query += " AND 1 = 0"

    prior_rows = fetch_all(
        query + " ORDER BY COALESCE(opened_at, created_at) DESC, id DESC LIMIT 25",
        tuple(params),
    )

    buckets: dict[str, int] = {}
    flag_counts: dict[str, int] = {}
    for row in prior_rows + [case]:
        bucket = row.get("state") or row.get("status") or "new"
        if bucket not in TERMINAL_STATES:
            bucket = "open"
        buckets[bucket] = buckets.get(bucket, 0) + 1
        for flag in json.loads(row.get("flags") or "[]"):
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    portfolio = (
        fetch_one("SELECT * FROM portfolios WHERE id = ?", (case["portfolio_id"],))
        if case.get("portfolio_id")
        else None
    )
    transaction_summary = None
    recent_transactions: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    alerts_count = 0
    if portfolio is not None:
        agg = fetch_one(
            """
            SELECT
                COUNT(id) AS count,
                COALESCE(SUM(total_amount), 0.0) AS total_amount,
                COALESCE(AVG(total_amount), 0.0) AS avg_amount,
                COALESCE(MAX(total_amount), 0.0) AS max_amount
            FROM transactions
            WHERE portfolio_id = ?
            """,
            (portfolio["id"],),
        )
        transaction_summary = {
            "count": int(agg["count"] or 0),
            "total_amount": float(agg["total_amount"] or 0.0),
            "avg_amount": float(agg["avg_amount"] or 0.0),
            "max_amount": float(agg["max_amount"] or 0.0),
        }
        recent_transactions = fetch_all(
            """
            SELECT id, symbol, transaction_type AS type, quantity, price, total_amount AS amount, fees, timestamp
            FROM transactions
            WHERE portfolio_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 10
            """,
            (portfolio["id"],),
        )
        assets = fetch_all(
            """
            SELECT symbol, name, quantity, current_price, asset_type
            FROM assets
            WHERE portfolio_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 25
            """,
            (portfolio["id"],),
        )
        alerts_row = fetch_one(
            "SELECT COUNT(*) AS count FROM alerts WHERE portfolio_id = ?",
            (portfolio["id"],),
        )
        alerts_count = int(alerts_row["count"]) if alerts_row else 0

    return {
        "subject_user": case.get("subject_user"),
        "summary": {
            "prior_case_count": len(prior_rows),
            "state_buckets": buckets,
            "sar_filed_count": buckets.get("closed_sar_filed", 0),
            "false_positive_count": buckets.get("closed_false_positive", 0),
            "open_case_count": buckets.get("open", 0),
            "top_flags": sorted(flag_counts.items(), key=lambda item: -item[1])[:6],
        },
        "prior_cases": [
            {
                "id": row["id"],
                "title": row.get("title"),
                "state": row.get("state") or row.get("status"),
                "priority": row.get("priority"),
                "risk_score": row.get("risk_score"),
                "risk_label": row.get("risk_label"),
                "opened_at": row.get("opened_at"),
                "closed_at": row.get("closed_at"),
            }
            for row in prior_rows
        ],
        "portfolio": {
            "id": portfolio["id"],
            "user_id": portfolio["user_id"],
            "name": portfolio["name"],
            "total_value": portfolio["total_value"],
            "cash_balance": portfolio["cash_balance"],
        }
        if portfolio
        else None,
        "transaction_summary": transaction_summary,
        "recent_transactions": recent_transactions,
        "assets": assets,
        "alerts_count": alerts_count,
    }
