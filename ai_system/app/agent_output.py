"""Shared helpers for consistent agent response metadata."""

from __future__ import annotations

from typing import Any


SEVERITY_ORDER = ("low", "medium", "high", "critical")
CONFIDENCE_LEVELS = ("low", "medium", "high")


def risk_severity(score: float | int | None = None, text: str | None = None) -> str:
    """Return a stable severity label from an explicit score or free text."""
    if score is not None:
        if score >= 80:
            return "critical"
        if score >= 55:
            return "high"
        if score >= 30:
            return "medium"
        return "low"

    lowered = (text or "").lower()
    for label in reversed(SEVERITY_ORDER):
        if label in lowered:
            return label
    return "unknown"


def normalize_list(values: list[Any] | tuple[Any, ...] | None, fallback: str) -> list[str]:
    items = [str(value).strip() for value in values or [] if str(value).strip()]
    return items or [fallback]


def build_structured_output(
    *,
    summary: str,
    severity: str = "unknown",
    confidence: str = "medium",
    key_factors: list[Any] | tuple[Any, ...] | None = None,
    recommended_actions: list[Any] | tuple[Any, ...] | None = None,
    follow_up: list[Any] | tuple[Any, ...] | None = None,
    raw_text: str | None = None,
) -> dict[str, Any]:
    """Build the standard agent output block while preserving simple fallbacks."""
    clean_summary = (summary or raw_text or "Analysis unavailable.").strip()
    clean_severity = severity if severity in (*SEVERITY_ORDER, "unknown") else "unknown"
    clean_confidence = confidence if confidence in CONFIDENCE_LEVELS else "medium"
    return {
        "summary": clean_summary,
        "severity": clean_severity,
        "confidence": clean_confidence,
        "key_factors": normalize_list(
            key_factors, "No specific driving factor was isolated."
        ),
        "recommended_actions": normalize_list(
            recommended_actions, "Continue analyst review using available case context."
        ),
        "follow_up": normalize_list(
            follow_up, "Document the rationale and monitor for material changes."
        ),
        "raw_text": raw_text or clean_summary,
    }
