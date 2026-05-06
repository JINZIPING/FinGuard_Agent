"""Typed contracts for inter-agent handoffs inside the LangGraph workflow."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


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
