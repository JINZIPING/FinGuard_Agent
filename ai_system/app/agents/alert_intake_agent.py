"""Alert intake logic aligned to the legacy prompts."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.analysis_utils import format_dict, format_list
from ai_system.app.llm import chat
from ai_system.app.ml import get_risk_engine


REQUIRED_ALERT_FIELDS = ("id", "timestamp")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _alert_contract(audience: str = "analyst") -> str:
    return (
        "Keep the response concise and action-oriented. Use these sections only:\n"
        "Summary: 1-2 sentences.\n"
        "Severity: low, medium, high, critical, or unknown.\n"
        "Confidence: low, medium, or high.\n"
        "Key factors: up to 3 bullets.\n"
        "Recommended actions: up to 3 bullets.\n"
        "Follow-up: up to 2 bullets.\n"
        f"Audience: {audience}."
    )


def _summary_from_text(text: str, fallback: str) -> str:
    clean = " ".join((text or fallback).split())
    if len(clean) <= 240:
        return clean
    return clean[:237].rstrip() + "..."


def _alert_prechecks(
    alert_source: str | None, alert_data: dict, ml_risk_info: dict | None = None
) -> dict:
    missing_fields = [
        field for field in REQUIRED_ALERT_FIELDS if not alert_data.get(field)
    ]
    amount = alert_data.get("amount") or alert_data.get("total_amount")
    large_amount = False
    try:
        large_amount = amount is not None and float(amount) >= 10000
    except (TypeError, ValueError):
        large_amount = False

    priority_hints: list[str] = []
    if missing_fields:
        priority_hints.append("missing_required_fields")
    if large_amount:
        priority_hints.append("large_amount")
    if ml_risk_info and ml_risk_info.get("risk_label") in {"high", "critical"}:
        priority_hints.append("elevated_ml_risk")
    if ml_risk_info and ml_risk_info.get("hard_block"):
        priority_hints.append("hard_block")

    return {
        "alert_source": alert_source or "unknown",
        "missing_fields": missing_fields,
        "large_amount": large_amount,
        "ml_risk_label": (ml_risk_info or {}).get("risk_label"),
        "ml_risk_score": (ml_risk_info or {}).get("risk_score"),
        "priority_hints": priority_hints,
    }


def _severity_from_prechecks(prechecks: dict, text: str = "") -> str:
    if "hard_block" in prechecks["priority_hints"]:
        return "critical"
    if "elevated_ml_risk" in prechecks["priority_hints"] or "large_amount" in prechecks["priority_hints"]:
        return "high"
    if prechecks["missing_fields"]:
        return "medium"
    return risk_severity(text=text) if text else "low"


def _actions_for_severity(severity: str) -> list[str]:
    if severity == "critical":
        return [
            "Route immediately to analyst review.",
            "Preserve ML scoring details and alert evidence.",
            "Open or update an escalation case if related alerts exist.",
        ]
    if severity == "high":
        return [
            "Prioritize for analyst review.",
            "Validate alert fields and related transaction context.",
            "Monitor for linked alerts or repeated activity.",
        ]
    if severity == "medium":
        return [
            "Complete missing alert details before closure.",
            "Document routing rationale.",
        ]
    return ["Continue standard alert triage."]


def process_alert(alert_source: str, alert_data: dict) -> dict:
    ml_section = ""
    ml_risk_info = None
    if alert_source in ("transaction", "payment", "transfer", "withdrawal"):
        engine = get_risk_engine()
        if engine:
            try:
                ml_result = engine.score(alert_data)
                ml_risk_info = {
                    "risk_score": ml_result["final_score"],
                    "risk_label": ml_result["risk_label"],
                    "method": ml_result["method"],
                    "hard_block": ml_result["hard_block"],
                    "flags": ml_result["flags"],
                }
                ml_section = (
                    f"\n\nML Risk Pre-Screening (hybrid engine):"
                    f"\n  Score: {ml_result['final_score']}/100"
                    f"\n  Label: {ml_result['risk_label']}"
                    f"\n  Method: {ml_result['method']}"
                    f"\n  Hard Block: {ml_result['hard_block']}"
                    f"\n  Flags: {', '.join(ml_result['flags']) or 'None'}"
                    f"\n\nConsider this ML score when assigning priority."
                )
            except Exception:
                pass

    prechecks = _alert_prechecks(alert_source, alert_data, ml_risk_info)
    prompt = f"""You are an alert intake specialist. Analyze this incoming financial alert and categorize it.

Alert Source: {alert_source}
Alert Details:
{format_dict(alert_data)}{ml_section}

Deterministic Prechecks:
{format_dict(prechecks)}

{_alert_contract("analyst")}

Categorize alert type, priority, affected area, and recommended routing."""
    result = chat(prompt)
    analysis = result or "Alert categorization unavailable."
    severity = _severity_from_prechecks(prechecks, analysis)
    response = {
        "agent": "AlertIntake",
        "timestamp": _timestamp(),
        "alert_type": alert_source,
        "analysis": analysis,
        "categorized": True,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(analysis, "Alert categorization unavailable."),
            severity=severity,
            confidence="high" if ml_risk_info else "medium",
            key_factors=prechecks["priority_hints"]
            or [f"Alert source: {alert_source or 'unknown'}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Re-check routing if additional alerts arrive."],
            raw_text=analysis,
        ),
    }
    if ml_risk_info:
        response["ml_risk"] = ml_risk_info
    return response


def filter_alerts(alerts: list) -> dict:
    prechecks = [
        _alert_prechecks(alert.get("source") or alert.get("type"), alert)
        for alert in alerts
    ]
    priority_count = sum(
        1 for item in prechecks if item["priority_hints"] or item["missing_fields"]
    )
    prompt = f"""You are reviewing {len(alerts)} financial alerts.

Alerts:
{format_list(alerts)}

Deterministic Prechecks:
{format_list(prechecks)}

{_alert_contract("analyst")}

Assess severity, escalation need, patterns, and prioritization."""
    result = chat(prompt)
    analysis = result or "Alert prioritization unavailable."
    severity = "high" if priority_count else risk_severity(text=analysis)
    return {
        "agent": "AlertIntake",
        "timestamp": _timestamp(),
        "original_count": len(alerts),
        "prioritized_analysis": analysis,
        "requires_escalation": "escalat" in analysis.lower(),
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(analysis, "Alert prioritization unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=[
                f"Alerts reviewed: {len(alerts)}",
                f"Alerts with priority hints: {priority_count}",
            ],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Review linked alerts as a group if escalation is needed."],
            raw_text=analysis,
        ),
    }


def validate_alert_integrity(alert: dict) -> dict:
    prechecks = _alert_prechecks(alert.get("source") or alert.get("type"), alert)
    prompt = f"""Validate the completeness and consistency of this financial alert:

{format_dict(alert)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_alert_contract("analyst")}

Validate required fields, data consistency, value ranges, conflicts, and timestamp validity."""
    result = chat(prompt)
    validation = result or "Alert validation unavailable."
    is_valid = not prechecks["missing_fields"] and "invalid" not in validation.lower()
    severity = _severity_from_prechecks(prechecks, validation)
    return {
        "agent": "AlertIntake",
        "timestamp": _timestamp(),
        "alert_id": alert.get("id"),
        "validation": validation,
        "is_valid": is_valid,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(validation, "Alert validation unavailable."),
            severity=severity,
            confidence="high",
            key_factors=prechecks["missing_fields"]
            or ["Required alert fields are present."],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Resolve validation gaps before alert closure."],
            raw_text=validation,
        ),
    }


class AlertIntakeAgent:
    AGENT_DOMAIN = "alert_intake"

    def process_alert(self, alert_source: str, alert_data: dict) -> dict:
        return process_alert(alert_source, alert_data)

    def filter_alerts(self, alerts: list) -> dict:
        return filter_alerts(alerts)

    def validate_alert_integrity(self, alert: dict) -> dict:
        return validate_alert_integrity(alert)
