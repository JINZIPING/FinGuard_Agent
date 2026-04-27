"""Escalation logic aligned to the legacy prompts."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.analysis_utils import format_dict, format_list
from ai_system.app.llm import chat


REGULATORY_MARKERS = ("aml", "kyc", "sar", "ofac", "sanction", "regulatory", "legal")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _escalation_contract(audience: str = "analyst") -> str:
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


def _combined_text(*items: object) -> str:
    return " ".join(str(item).lower() for item in items if item is not None)


def _escalation_prechecks(
    case_or_incident: dict | None = None,
    severity_factors: dict | None = None,
    *,
    related_count: int = 0,
    target_team: str | None = None,
) -> dict:
    case_or_incident = case_or_incident or {}
    severity_factors = severity_factors or {}
    text = _combined_text(case_or_incident, severity_factors, target_team)
    risk_score = case_or_incident.get("risk_score") or severity_factors.get("risk_score")
    try:
        risk_score = float(risk_score) if risk_score is not None else None
    except (TypeError, ValueError):
        risk_score = None
    regulatory_hints = [marker for marker in REGULATORY_MARKERS if marker in text]
    urgency_hints = [
        marker
        for marker in ("urgent", "critical", "sla", "overdue", "immediate")
        if marker in text
    ]
    customer_impact = any(
        marker in text for marker in ("customer impact", "loss", "blocked", "complaint")
    )
    missing_case_id = not bool(case_or_incident.get("id"))
    return {
        "missing_case_id": missing_case_id,
        "risk_score": risk_score,
        "regulatory_hints": regulatory_hints,
        "urgency_hints": urgency_hints,
        "customer_impact": customer_impact,
        "related_count": related_count,
        "target_team": target_team,
    }


def _severity_from_prechecks(prechecks: dict, text: str = "") -> str:
    if prechecks.get("risk_score") is not None:
        return risk_severity(prechecks["risk_score"], text)
    if prechecks["regulatory_hints"] and prechecks["urgency_hints"]:
        return "critical"
    if prechecks["regulatory_hints"] or prechecks["customer_impact"]:
        return "high"
    if prechecks["urgency_hints"] or prechecks["related_count"] >= 5:
        return "medium"
    return risk_severity(text=text) if text else "low"


def _actions_for_severity(severity: str) -> list[str]:
    if severity == "critical":
        return [
            "Escalate immediately to the responsible specialist team.",
            "Preserve evidence, timeline, and decision rationale.",
            "Confirm whether regulatory reporting or customer communication is required.",
        ]
    if severity == "high":
        return [
            "Queue for specialist review.",
            "Document facts, affected customer impact, and open questions.",
            "Monitor SLA and related-case activity.",
        ]
    if severity == "medium":
        return [
            "Assign owner and document follow-up tasks.",
            "Reassess if additional alerts, losses, or regulatory indicators appear.",
        ]
    return ["Continue standard case monitoring and document closure rationale."]


def evaluate_escalation_need(incident: dict, severity_factors: dict) -> dict:
    prechecks = _escalation_prechecks(incident, severity_factors)
    prompt = f"""Evaluate if this incident requires escalation:

Incident:
{format_dict(incident)}

Severity Factors:
{format_dict(severity_factors)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_escalation_contract("analyst")}

Evaluate severity, regulatory implications, customer impact, urgency, target team, and escalation path."""
    result = chat(prompt)
    evaluation = result or "Escalation evaluation unavailable."
    severity = _severity_from_prechecks(prechecks, evaluation)
    needs_escalation = severity in {"critical", "high"} or "escalat" in evaluation.lower()
    return {
        "agent": "EscalationCaseSummary",
        "timestamp": _timestamp(),
        "incident_id": incident.get("id"),
        "needs_escalation": needs_escalation,
        "evaluation": evaluation,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(evaluation, "Escalation evaluation unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=prechecks["regulatory_hints"]
            or prechecks["urgency_hints"]
            or [f"Risk score: {prechecks['risk_score']}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Reassess escalation if new evidence or SLA changes appear."],
            raw_text=evaluation,
        ),
    }


def generate_case_summary(case_data: dict, interactions: list, decisions: list) -> dict:
    prechecks = _escalation_prechecks(
        case_data,
        {"interaction_count": len(interactions), "decision_count": len(decisions)},
    )
    prompt = f"""Generate a comprehensive case summary:

Case Information:
{format_dict(case_data)}

Timeline of Interactions:
{format_list(interactions)}

Decisions Made:
{format_list(decisions)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_escalation_contract("analyst")}

Summarize overview, timeline, key facts, decisions, current status, open items, and handoff actions."""
    result = chat(prompt)
    summary = result or "Case summary unavailable."
    severity = _severity_from_prechecks(prechecks, summary)
    return {
        "agent": "EscalationCaseSummary",
        "timestamp": _timestamp(),
        "case_id": case_data.get("id"),
        "summary": summary,
        "ready_for_handoff": True,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(summary, "Case summary unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=[
                f"Interactions reviewed: {len(interactions)}",
                f"Decisions reviewed: {len(decisions)}",
            ],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Confirm handoff owner and next action due date."],
            raw_text=summary,
        ),
    }


def prepare_escalation_package(case: dict, target_team: str) -> dict:
    prechecks = _escalation_prechecks(case, target_team=target_team)
    prompt = f"""Prepare escalation package for {target_team} team:

Case:
{format_dict(case)}

Target Team: {target_team}

Deterministic Prechecks:
{format_dict(prechecks)}

{_escalation_contract("analyst")}

Tailor facts, evidence, timeline, specialist questions, regulatory notes, and next steps for the target team."""
    result = chat(prompt)
    package = result or "Escalation package unavailable."
    severity = _severity_from_prechecks(prechecks, package)
    return {
        "agent": "EscalationCaseSummary",
        "timestamp": _timestamp(),
        "case_id": case.get("id"),
        "target_team": target_team,
        "escalation_package": package,
        "prepared": True,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(package, "Escalation package unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=prechecks["regulatory_hints"]
            or [f"Target team: {target_team}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Send package to target team and track response."],
            raw_text=package,
        ),
    }


def summarize_case_resolution(case: dict, resolution: dict) -> dict:
    prechecks = _escalation_prechecks(case, resolution)
    prompt = f"""Summarize the resolution of this case:

Case:
{format_dict(case)}

Resolution:
{format_dict(resolution)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_escalation_contract("analyst")}

Document resolution, actions taken, outcomes, customer impact, lessons, preventive measures, and follow-up."""
    result = chat(prompt)
    resolution_summary = result or "Case resolution summary unavailable."
    severity = _severity_from_prechecks(prechecks, resolution_summary)
    return {
        "agent": "EscalationCaseSummary",
        "timestamp": _timestamp(),
        "case_id": case.get("id"),
        "resolution_summary": resolution_summary,
        "summarized": True,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(
                resolution_summary, "Case resolution summary unavailable."
            ),
            severity=severity,
            confidence="medium",
            key_factors=prechecks["regulatory_hints"]
            or ["Resolution record reviewed."],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Confirm closure state and retention requirements."],
            raw_text=resolution_summary,
        ),
    }


def identify_escalation_pattern(cases: list) -> dict:
    prechecks = _escalation_prechecks({}, {"case_count": len(cases)}, related_count=len(cases))
    prompt = f"""Analyze these cases for escalation patterns:

Cases:
{format_list(cases)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_escalation_contract("analyst")}

Identify common triggers, repeated customer/account patterns, process bottlenecks, policy gaps, and preventive controls."""
    result = chat(prompt)
    patterns = result or "Escalation pattern analysis unavailable."
    severity = _severity_from_prechecks(prechecks, patterns)
    return {
        "agent": "EscalationCaseSummary",
        "timestamp": _timestamp(),
        "patterns": patterns,
        "case_count": len(cases),
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(
                patterns, "Escalation pattern analysis unavailable."
            ),
            severity=severity,
            confidence="medium",
            key_factors=[f"Cases reviewed: {len(cases)}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Convert repeated patterns into control or workflow improvements."],
            raw_text=patterns,
        ),
    }


def draft_escalation_communication(case: dict, customer: dict, message_type: str) -> dict:
    prechecks = _escalation_prechecks(case, {"message_type": message_type})
    prompt = f"""Draft {message_type} escalation communication.

Case:
{format_dict(case)}

Customer:
{format_dict(customer)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_escalation_contract("analyst")}

Make the message clear, professional, and appropriate for the target audience."""
    result = chat(prompt)
    draft = result or "Escalation communication unavailable."
    severity = _severity_from_prechecks(prechecks, draft)
    return {
        "agent": "EscalationCaseSummary",
        "timestamp": _timestamp(),
        "case_id": case.get("id"),
        "message_type": message_type,
        "draft": draft,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(draft, "Escalation communication unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=[f"Message type: {message_type}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Review communication for legal, compliance, and customer-tone requirements."],
            raw_text=draft,
        ),
    }


class EscalationCaseSummaryAgent:
    AGENT_DOMAIN = "escalation"

    def evaluate_escalation_need(self, incident: dict, severity_factors: dict) -> dict:
        return evaluate_escalation_need(incident, severity_factors)

    def generate_case_summary(self, case_data: dict, interactions: list, decisions: list) -> dict:
        return generate_case_summary(case_data, interactions, decisions)

    def prepare_escalation_package(self, case: dict, target_team: str) -> dict:
        return prepare_escalation_package(case, target_team)

    def summarize_case_resolution(self, case: dict, resolution: dict) -> dict:
        return summarize_case_resolution(case, resolution)

    def identify_escalation_pattern(self, cases: list) -> dict:
        return identify_escalation_pattern(cases)

    def draft_escalation_communication(self, case: dict, customer: dict, message_type: str) -> dict:
        return draft_escalation_communication(case, customer, message_type)

