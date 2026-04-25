"""Customer context logic aligned to the legacy prompts."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.analysis_utils import format_dict, format_list
from ai_system.app.llm import chat


PROFILE_SIGNAL_FIELDS = (
    "risk_profile",
    "risk_tolerance",
    "investment_goals",
    "income",
    "net_worth",
    "segment",
    "portfolio_value",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _customer_contract(audience: str = "analyst") -> str:
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


def _profile_prechecks(customer_id: str | None, profile_data: dict) -> dict:
    present_fields = [
        field for field in PROFILE_SIGNAL_FIELDS if profile_data.get(field) not in (None, "")
    ]
    missing_id = not bool(customer_id)
    risk_indicators: list[str] = []
    risk_text = " ".join(str(value).lower() for value in profile_data.values())
    for marker in ("high-risk", "high risk", "enhanced", "sanction", "pep"):
        if marker in risk_text:
            risk_indicators.append(marker)
    return {
        "missing_customer_id": missing_id,
        "profile_field_count": len(profile_data),
        "signal_fields_present": present_fields,
        "profile_richness": "high" if len(present_fields) >= 4 else "medium" if len(present_fields) >= 2 else "low",
        "risk_indicators": sorted(set(risk_indicators)),
    }


def _interaction_prechecks(customer_id: str | None, interactions: list) -> dict:
    preference_markers = ("email", "phone", "sms", "app", "risk", "alert", "report")
    marker_hits = 0
    for item in interactions:
        text = str(item).lower()
        if any(marker in text for marker in preference_markers):
            marker_hits += 1
    return {
        "missing_customer_id": not bool(customer_id),
        "interaction_count": len(interactions),
        "preference_signal_count": marker_hits,
        "preference_completeness": "high" if marker_hits >= 3 else "medium" if marker_hits else "low",
    }


def _severity_from_prechecks(prechecks: dict, text: str = "") -> str:
    if prechecks.get("risk_indicators"):
        return "high"
    if prechecks.get("missing_customer_id"):
        return "medium"
    if prechecks.get("profile_richness") == "low" or prechecks.get("preference_completeness") == "low":
        return "medium"
    return risk_severity(text=text) if text else "low"


def _confidence_from_prechecks(prechecks: dict) -> str:
    if prechecks.get("profile_richness") == "high" or prechecks.get("preference_completeness") == "high":
        return "high"
    if prechecks.get("profile_richness") == "low" or prechecks.get("preference_completeness") == "low":
        return "low"
    return "medium"


def _actions_for_severity(severity: str) -> list[str]:
    if severity in {"critical", "high"}:
        return [
            "Route customer context to analyst review before high-impact decisions.",
            "Confirm KYC, risk profile, and recent behavior with source records.",
            "Apply enhanced monitoring if risk indicators are confirmed.",
        ]
    if severity == "medium":
        return [
            "Enrich the customer profile before relying on recommendations.",
            "Document assumptions used by downstream agents.",
        ]
    return ["Use the profile for routine context enrichment."]


def build_customer_profile(customer_id: str, profile_data: dict) -> dict:
    prechecks = _profile_prechecks(customer_id, profile_data)
    prompt = f"""You are a customer context specialist. Build a comprehensive profile:

Customer ID: {customer_id}
Available Data:
{format_dict(profile_data)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_customer_contract("analyst")}

Summarize financial situation, risk tolerance, goals, constraints, and downstream service context."""
    result = chat(prompt)
    profile = result or "Customer profile unavailable."
    severity = _severity_from_prechecks(prechecks, profile)
    return {
        "agent": "CustomerContext",
        "timestamp": _timestamp(),
        "customer_id": customer_id,
        "profile": profile,
        "profile_complete": True,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(profile, "Customer profile unavailable."),
            severity=severity,
            confidence=_confidence_from_prechecks(prechecks),
            key_factors=prechecks["risk_indicators"]
            or [f"Profile richness: {prechecks['profile_richness']}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Refresh customer context when KYC or portfolio data changes."],
            raw_text=profile,
        ),
    }


def get_customer_history(customer_id: str, history_type: str) -> dict:
    prechecks = {
        "missing_customer_id": not bool(customer_id),
        "history_type": history_type or "unknown",
        "profile_richness": "medium" if customer_id and history_type else "low",
    }
    prompt = f"""Retrieve and summarize {history_type} history for customer {customer_id}.

Deterministic Prechecks:
{format_dict(prechecks)}

{_customer_contract("analyst")}

Focus on recent patterns, anomalies, previous issues, interactions, and outcomes."""
    result = chat(prompt)
    context = result or "Customer history unavailable."
    severity = _severity_from_prechecks(prechecks, context)
    return {
        "agent": "CustomerContext",
        "timestamp": _timestamp(),
        "customer_id": customer_id,
        "history_type": history_type,
        "context": context,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(context, "Customer history unavailable."),
            severity=severity,
            confidence=_confidence_from_prechecks(prechecks),
            key_factors=[f"History type: {history_type or 'unknown'}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Attach source history before relying on historical conclusions."],
            raw_text=context,
        ),
    }


def assess_customer_needs(customer_id: str, current_situation: dict) -> dict:
    prechecks = _profile_prechecks(customer_id, current_situation)
    prompt = f"""Assess the current needs for customer {customer_id}:

Current Situation:
{format_dict(current_situation)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_customer_contract("analyst")}

Prioritize immediate needs, protection requirements, growth opportunities, compliance concerns, and service level."""
    result = chat(prompt)
    needs = result or "Customer needs assessment unavailable."
    severity = _severity_from_prechecks(prechecks, needs)
    return {
        "agent": "CustomerContext",
        "timestamp": _timestamp(),
        "customer_id": customer_id,
        "needs": needs,
        "assessed_at": "now",
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(needs, "Customer needs assessment unavailable."),
            severity=severity,
            confidence=_confidence_from_prechecks(prechecks),
            key_factors=prechecks["risk_indicators"]
            or [f"Profile richness: {prechecks['profile_richness']}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Review customer needs after major portfolio or life-event changes."],
            raw_text=needs,
        ),
    }


def extract_customer_preferences(customer_id: str, interactions: list) -> dict:
    prechecks = _interaction_prechecks(customer_id, interactions)
    prompt = f"""Extract and summarize preferences from customer {customer_id}'s interactions:

Interactions:
{format_list(interactions)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_customer_contract("analyst")}

Identify communication preferences, decision style, risk appetite, reporting preferences, and escalation preferences."""
    result = chat(prompt)
    preferences = result or "Customer preferences unavailable."
    severity = _severity_from_prechecks(prechecks, preferences)
    return {
        "agent": "CustomerContext",
        "timestamp": _timestamp(),
        "customer_id": customer_id,
        "preferences": preferences,
        "extracted": True,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(preferences, "Customer preferences unavailable."),
            severity=severity,
            confidence=_confidence_from_prechecks(prechecks),
            key_factors=[
                f"Interactions reviewed: {prechecks['interaction_count']}",
                f"Preference signals: {prechecks['preference_signal_count']}",
            ],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Refresh preferences after additional customer interactions."],
            raw_text=preferences,
        ),
    }


def get_customer_segment(profile: dict) -> dict:
    prechecks = _profile_prechecks(str(profile.get("customer_id") or ""), profile)
    prompt = f"""Determine customer segment based on profile:

{format_dict(profile)}

Deterministic Prechecks:
{format_dict(prechecks)}

{_customer_contract("analyst")}

Classify segment type, service tier, monitoring level, priority, and recommended service posture."""
    result = chat(prompt)
    segment = result or "Customer segment unavailable."
    severity = _severity_from_prechecks(prechecks, segment)
    return {
        "agent": "CustomerContext",
        "timestamp": _timestamp(),
        "segment": segment,
        "classified": True,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(segment, "Customer segment unavailable."),
            severity=severity,
            confidence=_confidence_from_prechecks(prechecks),
            key_factors=prechecks["risk_indicators"]
            or [f"Profile richness: {prechecks['profile_richness']}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Re-segment after material KYC, wealth, or risk-profile changes."],
            raw_text=segment,
        ),
    }


class CustomerContextAgent:
    AGENT_DOMAIN = "customer_context"

    def build_customer_profile(self, customer_id: str, profile_data: dict) -> dict:
        return build_customer_profile(customer_id, profile_data)

    def get_customer_history(self, customer_id: str, history_type: str) -> dict:
        return get_customer_history(customer_id, history_type)

    def assess_customer_needs(self, customer_id: str, current_situation: dict) -> dict:
        return assess_customer_needs(customer_id, current_situation)

    def extract_customer_preferences(self, customer_id: str, interactions: list) -> dict:
        return extract_customer_preferences(customer_id, interactions)

    def get_customer_segment(self, profile: dict) -> dict:
        return get_customer_segment(profile)
