"""Typed contracts and normalization helpers for LangGraph agent handoffs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, NotRequired, TypedDict, cast


CONTRACT_VERSION = "2026-05-06"


class StructuredAgentOutput(TypedDict):
    summary: str
    severity: str
    confidence: str
    key_factors: list[str]
    recommended_actions: list[str]
    follow_up: list[str]
    raw_text: str


class AgentArtifact(TypedDict):
    agent: str
    timestamp: str
    structured_output: StructuredAgentOutput
    analysis: NotRequired[str]
    summary: NotRequired[str]
    risk_analysis: NotRequired[str]
    assessment: NotRequired[str]
    prechecks: NotRequired[dict[str, Any]]
    findings: NotRequired[list[Any]]
    metrics: NotRequired[dict[str, Any]]
    consistency_score: NotRequired[int]
    consistency_label: NotRequired[str]
    behavioral_flags: NotRequired[list[str]]
    urgency_level: NotRequired[str]
    priority_tier: NotRequired[str]
    escalation_recommendation: NotRequired[str]
    action_recommendation: NotRequired[str]
    evidence_portfolio: NotRequired[list[str]]
    data_basis: NotRequired[dict[str, Any]]
    rate_limited: NotRequired[bool]
    success: NotRequired[bool]
    contract_version: NotRequired[str]


class Crew1Results(TypedDict):
    ml_scores: list[dict[str, Any]]
    risk_assessment: AgentArtifact
    risk_detection: AgentArtifact
    compliance: AgentArtifact


class Crew2Results(TypedDict):
    portfolio_analysis: AgentArtifact
    market_intelligence: AgentArtifact
    customer_context: AgentArtifact


class Crew3Results(TypedDict):
    alert_intake: AgentArtifact
    explanation: AgentArtifact
    escalation_evaluation: AgentArtifact
    escalation_case_summary: AgentArtifact


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _normalize_list(values: Any, fallback: str) -> list[str]:
    if isinstance(values, str):
        cleaned = values.strip()
        return [cleaned] if cleaned else [fallback]
    if isinstance(values, (list, tuple)):
        items = [str(value).strip() for value in values if str(value).strip()]
        return items or [fallback]
    return [fallback]


def normalize_structured_output(
    structured_output: dict[str, Any] | None,
    *,
    fallback_summary: str,
    fallback_raw_text: str | None = None,
) -> StructuredAgentOutput:
    payload = structured_output or {}
    raw_text = _clean_text(
        payload.get("raw_text") or fallback_raw_text or payload.get("summary"),
        fallback_summary,
    )
    summary = _clean_text(payload.get("summary"), raw_text)
    return {
        "summary": summary,
        "severity": _clean_text(payload.get("severity"), "unknown").lower(),
        "confidence": _clean_text(payload.get("confidence"), "medium").lower(),
        "key_factors": _normalize_list(
            payload.get("key_factors"),
            "No specific driving factor was isolated.",
        ),
        "recommended_actions": _normalize_list(
            payload.get("recommended_actions"),
            "Continue analyst review using available case context.",
        ),
        "follow_up": _normalize_list(
            payload.get("follow_up"),
            "Document the rationale and monitor for material changes.",
        ),
        "raw_text": raw_text,
    }


def normalize_agent_artifact(
    payload: dict[str, Any] | None,
    *,
    default_agent: str,
    primary_text_keys: tuple[str, ...] = ("summary", "analysis", "risk_analysis", "assessment"),
) -> AgentArtifact:
    artifact: dict[str, Any] = dict(payload or {})
    fallback_text = ""
    for key in primary_text_keys:
        value = artifact.get(key)
        if value:
            fallback_text = str(value)
            break
    fallback_summary = fallback_text.strip() or f"{default_agent} output unavailable."
    artifact["agent"] = _clean_text(artifact.get("agent"), default_agent)
    artifact["timestamp"] = _clean_text(artifact.get("timestamp"), _timestamp())
    artifact["structured_output"] = normalize_structured_output(
        cast(dict[str, Any] | None, artifact.get("structured_output")),
        fallback_summary=fallback_summary,
        fallback_raw_text=fallback_text or fallback_summary,
    )
    artifact["contract_version"] = _clean_text(
        artifact.get("contract_version"), CONTRACT_VERSION
    )
    if "evidence_portfolio" in artifact:
        artifact["evidence_portfolio"] = _normalize_list(
            artifact.get("evidence_portfolio"), "No evidence portfolio was captured."
        )
    if "behavioral_flags" in artifact:
        artifact["behavioral_flags"] = _normalize_list(
            artifact.get("behavioral_flags"), "No behavioral flag was isolated."
        )
    return cast(AgentArtifact, artifact)


def serialize_agent_artifact(payload: dict[str, Any] | None) -> dict[str, Any]:
    artifact = dict(payload or {})
    structured_output = dict(artifact.get("structured_output", {}) or {})
    artifact["structured_output"] = {
        "summary": structured_output.get("summary"),
        "severity": structured_output.get("severity"),
        "confidence": structured_output.get("confidence"),
        "key_factors": structured_output.get("key_factors", []),
        "recommended_actions": structured_output.get("recommended_actions", []),
        "follow_up": structured_output.get("follow_up", []),
        "raw_text": structured_output.get("raw_text"),
    }
    return artifact
