"""Risk logic aligned to the legacy hybrid scoring and recommendation flow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.analysis_utils import ml_score_transactions
from ai_system.app.llm import chat, is_rate_limit_error
from ai_system.app.ml import get_risk_engine


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _risk_contract(audience: str = "analyst") -> str:
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


def _severity_from_scores(scores: list[dict[str, Any]] | None, text: str = "") -> str:
    max_score = None
    for item in scores or []:
        value = item.get("final_score", item.get("risk_score"))
        if isinstance(value, (int, float)):
            max_score = value if max_score is None else max(max_score, value)
    return (
        risk_severity(max_score, text)
        if max_score is not None
        else risk_severity(text=text)
    )


def _actions_for_severity(severity: str) -> list[str]:
    if severity == "critical":
        return [
            "Hold or block the highest-risk activity pending senior review.",
            "Validate customer intent, counterparties, and related alerts.",
            "Open or update an escalation case with supporting evidence.",
        ]
    if severity == "high":
        return [
            "Queue for analyst review before closure.",
            "Compare flagged activity with recent customer and portfolio behavior.",
            "Escalate if similar indicators recur.",
        ]
    if severity == "medium":
        return [
            "Document the reviewed risk factors.",
            "Monitor for repeated transaction or allocation signals.",
        ]
    return ["Continue routine monitoring and retain the analysis rationale."]


def _score_factors(scores: list[dict[str, Any]] | None) -> list[str]:
    factors: list[str] = []
    labels: dict[str, int] = {}
    flags: dict[str, int] = {}
    for item in scores or []:
        label = str(item.get("risk_label") or "unknown")
        labels[label] = labels.get(label, 0) + 1
        for flag in item.get("flags", []) or []:
            flags[str(flag)] = flags.get(str(flag), 0) + 1
    if labels:
        factors.append(
            "Risk labels: "
            + ", ".join(f"{label}={count}" for label, count in sorted(labels.items()))
        )
    if flags:
        top_flags = sorted(flags.items(), key=lambda item: (-item[1], item[0]))[:3]
        factors.append(
            "Top flags: "
            + ", ".join(f"{flag} ({count})" for flag, count in top_flags)
        )
    return factors


def _score_transaction_risk(
    transaction: dict, customer_profile: dict | None = None
) -> dict:
    txn = {**transaction, **(customer_profile or {})}
    engine = get_risk_engine()
    if engine is not None:
        hybrid = engine.score(txn)
        llm_explanation = None
        if hybrid.get("needs_llm_review") or not hybrid["ml_details"].get("available"):
            llm_explanation = _llm_deep_dive(txn, hybrid)

        return {
            "transaction_id": transaction.get("id"),
            "final_score": hybrid["final_score"],
            "risk_label": hybrid["risk_label"],
            "method": hybrid["method"],
            "hard_block": hybrid["hard_block"],
            "flags": hybrid["flags"],
            "rule_score": hybrid["rule_details"]["rule_score"],
            "rule_flags": hybrid["rule_details"]["flags"],
            "rule_details": hybrid["rule_details"]["details"],
            "ml_risk_score": hybrid["ml_details"].get("ml_risk_score"),
            "ml_risk_label": hybrid["ml_details"].get("ml_risk_label"),
            "ml_fraud_flag": hybrid["ml_details"].get("ml_fraud_flag"),
            "ml_anomaly_score": hybrid["ml_details"].get("ml_anomaly_score"),
            "ml_confidence": hybrid["ml_details"].get("ml_confidence"),
            "ml_details": hybrid["ml_details"],
            "needs_llm_review": hybrid["needs_llm_review"],
            "llm_explanation": llm_explanation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    fallback = _score_via_llm(transaction, customer_profile or {})
    return {
        "transaction_id": fallback.get("transaction_id"),
        "final_score": fallback.get("final_score"),
        "risk_label": fallback.get("risk_label", "unknown"),
        "method": fallback.get("method", "llm_only"),
        "hard_block": fallback.get("hard_block", False),
        "flags": fallback.get("flags", []),
        "rule_score": None,
        "rule_flags": [],
        "rule_details": {},
        "ml_risk_score": None,
        "ml_risk_label": None,
        "ml_fraud_flag": None,
        "ml_anomaly_score": None,
        "ml_confidence": None,
        "ml_details": {"available": False, "reason": "ML engine unavailable"},
        "needs_llm_review": fallback.get("needs_llm_review", False),
        "llm_explanation": fallback.get("llm_explanation"),
        "timestamp": fallback.get("timestamp", datetime.now(timezone.utc).isoformat()),
    }


def _llm_deep_dive(txn: dict, hybrid_result: dict) -> str | None:
    prompt = f"""You are a senior financial risk analyst.

A transaction was scored by our automated system with a BORDERLINE result.
Provide a concise, actionable explanation of why this transaction may or
may not be risky, and recommend next steps.

Transaction Summary:
  Amount:             ${txn.get("amount", "N/A"):,.2f}
  Type:               {txn.get("transaction_type", "N/A")}
  Sender Country:     {txn.get("sender_country", "N/A")}
  Receiver Country:   {txn.get("receiver_country", "N/A")}
  Asset Type:         {txn.get("asset_type", "N/A")}
  Channel:            {txn.get("channel", "N/A")}
  Account Age (days): {txn.get("account_age_days", "N/A")}
  Is New Payee:       {txn.get("is_new_payee", "N/A")}

Automated Scoring:
  Combined Score:     {hybrid_result["final_score"]}/100
  Rule Flags:         {", ".join(hybrid_result["flags"]) or "None"}
  ML Risk Label:      {hybrid_result["ml_details"].get("ml_risk_label", "N/A")}
  ML Fraud Flag:      {hybrid_result["ml_details"].get("ml_fraud_flag", "N/A")}

{_risk_contract("analyst")}

Recommended action must be one of: APPROVE, HOLD_FOR_REVIEW, ESCALATE, BLOCK."""
    return chat(prompt)


def _score_via_llm(transaction: dict, customer_profile: dict) -> dict:
    prompt = f"""Score the risk level of this transaction:

Transaction:
{json.dumps(transaction, indent=2)}

Customer Profile:
{json.dumps(customer_profile, indent=2)}

{_risk_contract("analyst")}

Estimate risk score from 1-100 and include the recommended action."""
    result = chat(prompt)
    return {
        "agent": "RiskAssessment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transaction_id": transaction.get("id"),
        "final_score": None,
        "risk_label": "unknown",
        "method": "llm_only",
        "hard_block": False,
        "flags": [],
        "llm_explanation": result,
        "needs_llm_review": False,
        "flagged": "high" in (result or "").lower(),
    }


def score_transaction(transaction: dict, customer_profile: dict | None = None) -> dict:
    engine = get_risk_engine()
    if engine is not None:
        hybrid = engine.score({**transaction, **(customer_profile or {})})
        result = {
            "rule_score": hybrid["rule_details"]["rule_score"],
            "rule_flags": hybrid["rule_details"]["flags"],
            "rule_details": hybrid["rule_details"]["details"],
            "ml_risk_score": hybrid["ml_details"].get("ml_risk_score"),
            "ml_risk_label": hybrid["ml_details"].get("ml_risk_label"),
            "ml_fraud_flag": hybrid["ml_details"].get("ml_fraud_flag"),
            "ml_anomaly_score": hybrid["ml_details"].get("ml_anomaly_score"),
            "ml_confidence": hybrid["ml_details"].get("ml_confidence"),
            "ml_details": hybrid["ml_details"],
            "final_score": hybrid["final_score"],
            "risk_label": hybrid["risk_label"],
            "method": hybrid["method"],
            "hard_block": hybrid["hard_block"],
            "flags": hybrid["flags"],
            "needs_llm_review": hybrid["needs_llm_review"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    else:
        try:
            result = _score_transaction_risk(transaction, customer_profile)
        except Exception as exc:
            result = {
                "final_score": None,
                "risk_label": "unknown",
                "method": "llm_only",
                "hard_block": False,
                "flags": [],
                "needs_llm_review": False,
                "rule_score": None,
                "rule_flags": [],
                "rule_details": {},
                "ml_risk_score": None,
                "ml_risk_label": None,
                "ml_fraud_flag": None,
                "ml_anomaly_score": None,
                "ml_confidence": None,
                "ml_details": {"available": False, "reason": str(exc)},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    return {
        "risk_score": result["final_score"],
        "risk_label": result["risk_label"],
        "method": result["method"],
        "hard_block": result["hard_block"],
        "flags": result["flags"],
        "needs_llm_review": result["needs_llm_review"],
        "rule_details": {
            "rule_score": result.get("rule_score"),
            "flags": result.get("rule_flags", []),
            "details": result.get("rule_details", {}),
        },
        "ml_details": {
            "ml_risk_score": result.get("ml_risk_score"),
            "ml_risk_label": result.get("ml_risk_label"),
            "ml_fraud_flag": result.get("ml_fraud_flag"),
            "ml_anomaly_score": result.get("ml_anomaly_score"),
            "ml_confidence": result.get("ml_confidence"),
            "available": result.get("ml_details", {}).get("available"),
            "reason": result.get("ml_details", {}).get("reason"),
        },
        "timestamp": result["timestamp"],
    }


def score_transaction_risk(
    transaction: dict, customer_profile: dict | None = None
) -> dict:
    return _score_transaction_risk(transaction, customer_profile)


def assess_portfolio_risk(
    portfolio_data: dict,
    market_conditions: dict,
    customer_context: dict | None = None,
) -> dict:
    prompt = f"""You are a risk assessment expert. Perform comprehensive portfolio risk assessment:

Portfolio:
{json.dumps(portfolio_data, indent=2)}

Market Conditions:
{json.dumps(market_conditions, indent=2)}

Customer Context:
{json.dumps(customer_context or {}, indent=2)}

{_risk_contract("analyst")}

Focus on concentration, liquidity, market sensitivity, and practical mitigations."""
    result = chat(prompt)
    risk_analysis = result or "Risk assessment unavailable."
    severity = risk_severity(text=risk_analysis)
    return {
        "agent": "RiskAssessment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assessment_type": "portfolio",
        "risk_analysis": risk_analysis,
        "complete": True,
        "structured_output": build_structured_output(
            summary=_summary_from_text(risk_analysis, "Risk assessment unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=[
                f"Assets reviewed: {len(portfolio_data.get('assets', []))}",
                f"Total value: {portfolio_data.get('total_value', 'unknown')}",
                f"Market context supplied: {'yes' if market_conditions else 'no'}",
            ],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Reassess after major allocation or market-condition changes."],
            raw_text=risk_analysis,
        ),
    }


def detect_fraud_risk(
    transaction_history: list[dict[str, Any]],
    portfolio_data: dict[str, Any],
    ml_pre_scores: list[dict[str, Any]] | None = None,
) -> dict:
    ml_summary_lines: list[str] = []
    if ml_pre_scores:
        for index, result in enumerate(ml_pre_scores):
            ml_summary_lines.append(
                f"  Txn {index + 1}: score={result.get('final_score', result.get('risk_score', '?'))}/100 "
                f"label={result.get('risk_label', '?')} "
                f"flags=[{', '.join(result.get('flags', []))}]"
            )
    else:
        engine = get_risk_engine()
        if engine:
            for index, txn in enumerate(transaction_history[:20]):
                try:
                    result = engine.score(txn)
                    ml_summary_lines.append(
                        f"  Txn {index + 1}: score={result['final_score']}/100 "
                        f"label={result['risk_label']} method={result['method']} "
                        f"flags=[{', '.join(result['flags'])}]"
                    )
                except Exception:
                    ml_summary_lines.append(f"  Txn {index + 1}: ML scoring failed")

    ml_section = ""
    if ml_summary_lines:
        ml_section = (
            "\n\n-- ML Pre-Screening Results (Rules + GradientBoosting + IsolationForest) --\n"
            + "\n".join(ml_summary_lines)
            + "\n\nUse these ML scores as your baseline. Add expert analysis on top."
        )

    prompt = (
        "You are a financial fraud detection expert. Analyse these transactions "
        "and portfolio for suspicious activity:\n\n"
        f"Transaction History:\n{json.dumps(transaction_history[:10], indent=2)}\n\n"
        f"Portfolio Data:\n{json.dumps(portfolio_data, indent=2)}"
        f"{ml_section}\n\n"
        f"{_risk_contract('analyst')}\n\n"
        "Identify unusual transaction patterns, fraud indicators, specific alerts, "
        "and recommended actions."
    )
    response = chat(prompt)
    assessment = response or "Fraud analysis unavailable."
    severity = _severity_from_scores(ml_pre_scores, assessment)
    key_factors = _score_factors(ml_pre_scores)
    key_factors.append(f"Transactions reviewed: {len(transaction_history[:10])}")
    return {
        "agent": "RiskDetector",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_type": "fraud_risk",
        "assessment": assessment,
        "structured_output": build_structured_output(
            summary=_summary_from_text(assessment, "Fraud analysis unavailable."),
            severity=severity,
            confidence="high" if ml_pre_scores else "medium",
            key_factors=key_factors,
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Compare future activity against the same fraud indicators."],
            raw_text=assessment,
        ),
    }


def assess_market_risk(portfolio_data: dict[str, Any], market_conditions: dict[str, Any]) -> dict:
    prompt = (
        "You are a market risk analyst. Assess portfolio risk in current "
        "market conditions:\n\n"
        f"Portfolio:\n{json.dumps(portfolio_data, indent=2)}\n\n"
        f"Market Conditions:\n{json.dumps(market_conditions, indent=2)}\n\n"
        f"{_risk_contract('analyst')}\n\n"
        "Assess market exposure, sector-specific risks, systemic risk, and protective measures."
    )
    response = chat(prompt)
    assessment = response or "Market risk assessment unavailable."
    severity = risk_severity(text=assessment)
    return {
        "agent": "RiskDetector",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_type": "market_risk",
        "assessment": assessment,
        "structured_output": build_structured_output(
            summary=_summary_from_text(
                assessment, "Market risk assessment unavailable."
            ),
            severity=severity,
            confidence="medium",
            key_factors=[
                f"Assets reviewed: {len(portfolio_data.get('assets', []))}",
                f"Market fields supplied: {len(market_conditions)}",
            ],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Refresh market assumptions before making trading decisions."],
            raw_text=assessment,
        ),
    }


def identify_systemic_risks(market_data: dict, portfolio_exposures: list) -> dict:
    prompt = f"""Identify systemic risks affecting our customers:

Market Data:
{json.dumps(market_data, indent=2)}

Customer Exposures:
{json.dumps(portfolio_exposures, indent=2)}

Analyze:
1. Market-wide risks
2. Sector correlation risks
3. Geographic concentration risks
4. Counterparty concentration
5. Liquidity shocks
6. Black swan scenarios
7. Customer impact assessment

Return systemic risk report with mitigation strategies."""
    result = chat(prompt)
    return {
        "agent": "RiskAssessment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "analysis": "systemic",
        "risks_identified": result or "Systemic risk analysis unavailable.",
        "requires_action": True,
    }


def calculate_risk_metrics(portfolio: dict) -> dict:
    prompt = f"""Calculate key risk metrics for this portfolio:

{json.dumps(portfolio, indent=2)}

Calculate:
1. Value at Risk (VaR) at 95% and 99%
2. Sharpe Ratio
3. Sortino Ratio
4. Maximum Drawdown
5. Correlation matrix key findings
6. Beta vs benchmark
7. Duration (if fixed income)

Return metrics with interpretations."""
    result = chat(prompt)
    return {
        "agent": "RiskAssessment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": result or "Risk metrics unavailable.",
        "calculated": True,
    }


def recommend_hedging_strategies(risks: dict, constraints: dict) -> dict:
    prompt = f"""Recommend hedging strategies for identified risks:

Identified Risks:
{json.dumps(risks, indent=2)}

Constraints:
{json.dumps(constraints, indent=2)}

Recommend:
1. Hedging instruments
2. Allocation amounts
3. Cost-benefit analysis
4. Implementation timeline
5. Monitoring approach
6. Alternatives if primary not available

Return prioritized hedging strategy."""
    result = chat(prompt)
    return {
        "agent": "RiskAssessment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "strategies": result or "Hedging strategy unavailable.",
        "recommended": True,
    }


def quick_portfolio_recommendation(
    portfolio_data: dict[str, Any], transactions: list[dict[str, Any]]
) -> dict:
    portfolio_summary = (
        f"Portfolio '{portfolio_data.get('name')}': "
        f"${portfolio_data.get('total_value', 0):,.0f}, "
        f"{len(portfolio_data.get('assets', []))} assets"
    )
    ml_summary = ml_score_transactions(transactions[:5])

    try:
        prompt = (
            "Quick risk assessment for an analyst:\n"
            f"{portfolio_summary}\n"
            f"{ml_summary}\n\n"
            f"{_risk_contract('analyst')}\n"
            "Be direct about whether the portfolio needs routine monitoring, review, or escalation."
        )
        recommendation = chat(prompt)
        severity = risk_severity(text=f"{recommendation}\n{ml_summary}")
        crew_output = (
            "## ? Quick Recommendation\n\n"
            f"**Portfolio:** {portfolio_summary}\n\n"
            f"### AI Risk Assessment\n{recommendation}\n\n"
            f"### ML Pre-Screening\n{ml_summary}\n\n"
            "**Next Steps:**\n"
            "• Run full analysis for comprehensive review\n"
            "• Or increase your model service quota if the full path is rate-limited"
        )
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "portfolio_id": portfolio_data.get("id"),
            "crew_output": crew_output,
            "recommendation": recommendation,
            "agents_used": 1,
            "recommendation_type": "quick",
            "rate_limited": False,
            "structured_output": build_structured_output(
                summary=_summary_from_text(
                    recommendation, "Quick recommendation unavailable."
                ),
                severity=severity,
                confidence="medium",
                key_factors=[
                    portfolio_summary,
                    "ML pre-screening supplied: " + ("yes" if ml_summary else "no"),
                ],
                recommended_actions=_actions_for_severity(severity),
                follow_up=["Run full analysis before making high-impact decisions."],
                raw_text=crew_output,
            ),
        }
    except Exception as exc:
        if is_rate_limit_error(exc):
            fallback = (
                "?? **Rate Limit Reached**\n\n"
                "Even the quick recommendation exceeded the rate limit.\n"
                "Please wait 30-60 seconds and try again, or increase your model service quota.\n\n"
                f"{ml_summary}"
            )
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "portfolio_id": portfolio_data.get("id"),
                "crew_output": fallback,
                "agents_used": 0,
                "recommendation_type": "quick",
                "rate_limited": True,
                "structured_output": build_structured_output(
                    summary="Quick recommendation was rate limited; ML pre-screening remains available.",
                    severity=risk_severity(text=ml_summary),
                    confidence="low",
                    key_factors=["LLM recommendation unavailable due to rate limiting."],
                    recommended_actions=["Retry after the model service recovers."],
                    follow_up=["Use full analysis once quota is available."],
                    raw_text=fallback,
                ),
            }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "portfolio_id": portfolio_data.get("id"),
            "crew_output": f"? Quick recommendation failed: {str(exc)[:200]}",
            "agents_used": 0,
            "recommendation_type": "quick",
            "error": str(exc),
            "structured_output": build_structured_output(
                summary="Quick recommendation failed before an analyst narrative could be generated.",
                severity="unknown",
                confidence="low",
                key_factors=[str(exc)[:200]],
                recommended_actions=["Retry the request or run deterministic transaction scoring."],
                follow_up=["Check model configuration if the failure repeats."],
                raw_text=str(exc),
            ),
        }


def invoke(portfolio: dict, transactions: list[dict], mode: str = "quick") -> dict:
    findings = []
    scored = [_score_transaction_risk(txn) for txn in transactions[:10]]
    available_scores = [item for item in scored if item["final_score"] is not None]

    if available_scores:
        high = [
            item
            for item in available_scores
            if item["risk_label"] in {"high", "critical"}
        ]
        medium = [item for item in available_scores if item["risk_label"] == "medium"]
        if high:
            findings.append(
                f"{len(high)} recent transactions scored high or critical risk."
            )
        elif medium:
            findings.append(
                f"{len(medium)} recent transactions scored medium risk and may need review."
            )
        else:
            findings.append(
                "Hybrid scoring did not surface any high-risk recent transaction."
            )
    else:
        findings.append(
            "Quick risk screen did not detect any strong operational risk signal."
        )

    severity = _severity_from_scores(scored)
    return {
        "agent": "risk",
        "mode": mode,
        "summary": " ".join(findings),
        "findings": findings,
        "scored_transactions": scored,
        "structured_output": build_structured_output(
            summary=" ".join(findings),
            severity=severity,
            confidence="high" if available_scores else "medium",
            key_factors=_score_factors(scored) + findings,
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Review scored transactions if new alerts or cases appear."],
            raw_text=" ".join(findings),
        ),
    }


class RiskAssessmentAgent:
    AGENT_DOMAIN = "risk_assessment"

    def assess_portfolio_risk(
        self,
        portfolio_data: dict,
        market_conditions: dict,
        customer_context: dict | None = None,
    ) -> dict:
        return assess_portfolio_risk(
            portfolio_data, market_conditions, customer_context
        )

    def score_transaction_risk(self, transaction: dict, customer_profile: dict | None = None) -> dict:
        return score_transaction_risk(transaction, customer_profile)

    def identify_systemic_risks(self, market_data: dict, portfolio_exposures: list) -> dict:
        return identify_systemic_risks(market_data, portfolio_exposures)

    def calculate_risk_metrics(self, portfolio: dict) -> dict:
        return calculate_risk_metrics(portfolio)

    def recommend_hedging_strategies(self, risks: dict, constraints: dict) -> dict:
        return recommend_hedging_strategies(risks, constraints)


class RiskDetectionAgent:
    AGENT_DOMAIN = "risk_detection"

    def detect_fraud_risk(
        self,
        transaction_history: list[dict[str, Any]],
        portfolio_data: dict[str, Any],
        ml_pre_scores: list[dict[str, Any]] | None = None,
    ) -> dict:
        return detect_fraud_risk(transaction_history, portfolio_data, ml_pre_scores)

    def assess_market_risk(self, portfolio_data: dict[str, Any], market_conditions: dict[str, Any]) -> dict:
        return assess_market_risk(portfolio_data, market_conditions)

