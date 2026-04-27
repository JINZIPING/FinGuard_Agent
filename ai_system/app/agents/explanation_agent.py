"""Explanation logic aligned to the legacy prompts."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.analysis_utils import format_dict
from ai_system.app.llm import chat


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_contract(audience: str = "analyst") -> str:
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


def _factor_items(factors: dict) -> list[str]:
    return [f"{key}: {value}" for key, value in factors.items()]


def _actions_for_score(score: float) -> list[str]:
    if score >= 80:
        return [
            "Block or hold the transaction pending senior review.",
            "Validate customer intent and counterparty details.",
            "Open or update an escalation case with the risk rationale.",
        ]
    if score >= 55:
        return [
            "Hold for analyst review before closure.",
            "Compare with recent customer activity and related alerts.",
            "Escalate if similar activity repeats or corroborating flags appear.",
        ]
    if score >= 30:
        return [
            "Monitor the account for related activity.",
            "Document the reviewed factors and decision rationale.",
        ]
    return ["Continue routine monitoring and retain the scoring rationale."]


def invoke(portfolio: dict, transactions: list[dict], findings: list[str]) -> dict:
    if findings:
        narrative = (
            f"Portfolio '{portfolio.get('name', 'Unnamed Portfolio')}' was reviewed across "
            f"{len(transactions)} recent transactions. " + " ".join(findings)
        )
    else:
        narrative = (
            f"Portfolio '{portfolio.get('name', 'Unnamed Portfolio')}' was reviewed and "
            "no material finding was surfaced in the quick path."
        )

    return {
        "agent": "Explanation",
        "timestamp": _timestamp(),
        "summary": narrative,
        "structured_output": build_structured_output(
            summary=narrative,
            severity=risk_severity(text=narrative),
            confidence="medium",
            key_factors=findings,
            recommended_actions=["Review the findings and document the decision."],
            follow_up=["Re-run analysis if new transactions or alerts appear."],
            raw_text=narrative,
        ),
    }


def explain_alert(alert: dict, audience: str = "customer") -> dict:
    prompt = f"""Explain this financial alert for a {audience} audience:

Alert:
{format_dict(alert)}

{_agent_contract(audience)}

Explain why the alert matters without overstating certainty. Avoid unnecessary jargon."""
    result = chat(prompt)
    explanation = result or "Alert explanation unavailable."
    return {
        "agent": "Explanation",
        "timestamp": _timestamp(),
        "alert_id": alert.get("id"),
        "audience": audience,
        "explanation": explanation,
        "structured_output": build_structured_output(
            summary=_summary_from_text(explanation, "Alert explanation unavailable."),
            severity=risk_severity(text=explanation),
            confidence="medium",
            key_factors=[
                "Alert source: " + str(alert.get("source") or alert.get("type") or "unknown"),
                "Alert id: " + str(alert.get("id") or "not provided"),
            ],
            recommended_actions=["Review the alert context and document the disposition."],
            follow_up=["Escalate if the alert aligns with other recent risk signals."],
            raw_text=explanation,
        ),
    }


def explain_recommendation(recommendation: dict, customer_profile: dict) -> dict:
    prompt = f"""Explain why this recommendation is suitable:

Recommendation:
{format_dict(recommendation)}

Customer Profile:
{format_dict(customer_profile)}

{_agent_contract("analyst")}

Explain suitability, risk implications, and next steps. Avoid investment certainty."""
    result = chat(prompt)
    explanation = result or "Recommendation explanation unavailable."
    return {
        "agent": "Explanation",
        "timestamp": _timestamp(),
        "recommendation_id": recommendation.get("id"),
        "explained": True,
        "explanation": explanation,
        "structured_output": build_structured_output(
            summary=_summary_from_text(
                explanation, "Recommendation explanation unavailable."
            ),
            severity=risk_severity(text=explanation),
            confidence="medium",
            key_factors=[
                "Recommendation type: "
                + str(recommendation.get("action") or recommendation.get("type") or "unknown"),
                "Customer profile supplied: " + ("yes" if customer_profile else "no"),
            ],
            recommended_actions=["Confirm suitability against the customer profile."],
            follow_up=["Document alternatives considered before acting."],
            raw_text=explanation,
        ),
    }


def explain_risk_score(transaction: dict, score: float, factors: dict) -> dict:
    prompt = f"""Explain this transaction risk score:

Transaction:
{format_dict(transaction)}

Risk Score: {score}/100

Contributing Factors:
{format_dict(factors)}

{_agent_contract("analyst")}

Explain what the score means, which factors drove it, and what should happen next."""
    result = chat(prompt)
    explanation = result or "Risk score explanation unavailable."
    severity = risk_severity(score)
    return {
        "transaction_id": transaction.get("id"),
        "score_explained": score,
        "explanation": explanation,
        "agent": "Explanation",
        "timestamp": _timestamp(),
        "structured_output": build_structured_output(
            summary=_summary_from_text(explanation, "Risk score explanation unavailable."),
            severity=severity,
            confidence="high" if factors else "medium",
            key_factors=_factor_items(factors),
            recommended_actions=_actions_for_score(score),
            follow_up=["Reassess if new related activity appears."],
            raw_text=explanation,
        ),
    }


def explain_portfolio_performance(portfolio: dict, performance: dict) -> dict:
    prompt = f"""Explain this portfolio's performance to the customer:

Portfolio:
{format_dict(portfolio)}

Performance:
{format_dict(performance)}

{_agent_contract("customer")}

Explain overall performance, important drivers, and practical next steps."""
    result = chat(prompt)
    explanation = result or "Portfolio performance explanation unavailable."
    return {
        "agent": "Explanation",
        "timestamp": _timestamp(),
        "portfolio_id": portfolio.get("id"),
        "explained": True,
        "explanation": explanation,
        "structured_output": build_structured_output(
            summary=_summary_from_text(
                explanation, "Portfolio performance explanation unavailable."
            ),
            severity=risk_severity(text=explanation),
            confidence="medium",
            key_factors=[
                "Portfolio: " + str(portfolio.get("name") or portfolio.get("id") or "unknown"),
                "Performance data supplied: " + ("yes" if performance else "no"),
            ],
            recommended_actions=["Review allocation, liquidity, and concentration drivers."],
            follow_up=["Revisit the explanation after updated performance data is available."],
            raw_text=explanation,
        ),
    }


def explain_compliance_finding(finding: dict, customer_context: dict) -> dict:
    prompt = f"""Explain this compliance issue to the customer:

Finding:
{format_dict(finding)}

Customer Context:
{format_dict(customer_context)}

{_agent_contract("customer")}

Explain the issue, why it matters, what happens next, and what the customer needs to do."""
    result = chat(prompt)
    explanation = result or "Compliance finding explanation unavailable."
    return {
        "agent": "Explanation",
        "timestamp": _timestamp(),
        "finding_id": finding.get("id"),
        "explained": True,
        "explanation": explanation,
        "structured_output": build_structured_output(
            summary=_summary_from_text(
                explanation, "Compliance finding explanation unavailable."
            ),
            severity=risk_severity(text=explanation),
            confidence="medium",
            key_factors=[
                "Finding id: " + str(finding.get("id") or "not provided"),
                "Customer context supplied: " + ("yes" if customer_context else "no"),
            ],
            recommended_actions=["Resolve the compliance finding through the documented workflow."],
            follow_up=["Escalate if regulatory or customer-impact concerns remain unresolved."],
            raw_text=explanation,
        ),
    }


def explain_transaction_risk(transaction: dict, score: float, factors: dict) -> dict:
    try:
        result = explain_risk_score(transaction, score, factors)
        return {
            "insights": result.get("explanation", ""),
            "agent": "Explanation",
            "timestamp": result.get(
                "timestamp", _timestamp()
            ),
            "success": True,
            "structured_output": result.get("structured_output"),
        }
    except Exception as exc:
        error_msg = str(exc)

    severity = risk_severity(score)
    fallback_insights = (
        f"**Risk Assessment Summary**\n"
        f"Risk Score: {score}/100\n"
        f"Risk Level: {severity.upper()}\n\n"
        f"**Contributing Factors**\n"
    )
    for key, value in factors.items():
        fallback_insights += f"- {key}: {value}\n"
    fallback_insights += f"\n**Analysis**\nThe combination of these factors indicates {severity} risk. "
    if score >= 80:
        fallback_insights += (
            "Immediate action is recommended:\n"
            "- Review transaction details carefully\n"
            "- Consider blocking the transaction\n"
            "- Contact the customer if appropriate"
        )
    elif score >= 55:
        fallback_insights += (
            "Further investigation recommended:\n"
            "- Gather additional context\n"
            "- Monitor for related activity\n"
            "- Escalate if patterns emerge"
        )
    else:
        fallback_insights += "Continue routine monitoring."
    return {
        "insights": fallback_insights,
        "agent": "Explanation",
        "timestamp": _timestamp(),
        "success": False,
        "error_reason": error_msg,
        "structured_output": build_structured_output(
            summary=f"Transaction risk explanation fell back to deterministic guidance for a {severity} risk score.",
            severity=severity,
            confidence="medium",
            key_factors=_factor_items(factors),
            recommended_actions=_actions_for_score(score),
            follow_up=["Retry LLM explanation later if a narrative note is still needed."],
            raw_text=fallback_insights,
        ),
    }


def summarize_analysis(analysis_results: dict, detail_level: str = "medium") -> dict:
    prompt = f"""Summarize this analysis at {detail_level} detail level:

Analysis Results:
{format_dict(analysis_results)}

{_agent_contract("analyst")}

Detail level: {detail_level}. Prioritize operational next steps over long narrative."""
    result = chat(prompt)
    summary = result or "Summary unavailable."
    return {
        "agent": "Explanation",
        "timestamp": _timestamp(),
        "summary": summary,
        "detail_level": detail_level,
        "structured_output": build_structured_output(
            summary=_summary_from_text(summary, "Summary unavailable."),
            severity=risk_severity(text=summary),
            confidence="medium",
            key_factors=["Crew analysis results were reviewed."],
            recommended_actions=["Review the summarized findings and assign ownership."],
            follow_up=["Monitor for repeated risk indicators in future runs."],
            raw_text=summary,
        ),
    }


class ExplanationAgent:
    AGENT_DOMAIN = "explanation"

    def explain_alert(self, alert: dict, audience: str = "customer") -> dict:
        return explain_alert(alert, audience)

    def explain_recommendation(self, recommendation: dict, customer_profile: dict) -> dict:
        return explain_recommendation(recommendation, customer_profile)

    def explain_risk_score(self, transaction: dict, score: float, factors: dict) -> dict:
        return explain_risk_score(transaction, score, factors)

    def explain_portfolio_performance(self, portfolio: dict, performance: dict) -> dict:
        return explain_portfolio_performance(portfolio, performance)

    def explain_compliance_finding(self, finding: dict, customer_context: dict) -> dict:
        return explain_compliance_finding(finding, customer_context)

    def summarize_analysis(self, analysis_results: dict, detail_level: str = "medium") -> dict:
        return summarize_analysis(analysis_results, detail_level)

