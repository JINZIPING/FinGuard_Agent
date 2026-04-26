"""Risk logic aligned to the legacy hybrid scoring and recommendation flow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ai_system.app.analysis_utils import ml_score_transactions
from ai_system.app.llm import chat, is_rate_limit_error
from ai_system.app.ml import get_risk_engine


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

Provide:
1. Plain-language risk explanation (2-3 sentences)
2. Recommended action: APPROVE / HOLD_FOR_REVIEW / ESCALATE / BLOCK
3. Key factors driving the score"""
    return chat(prompt)


def _score_via_llm(transaction: dict, customer_profile: dict) -> dict:
    prompt = f"""Score the risk level of this transaction:

Transaction:
{json.dumps(transaction, indent=2)}

Customer Profile:
{json.dumps(customer_profile, indent=2)}

Evaluate:
1. Deviation from customer norm
2. Fraud indicators
3. AML/KYC concerns
4. Regulatory red flags
5. Risk score (1-100)
6. Action recommendations

Return risk score and required actions."""
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


def assess_portfolio_risk(portfolio_data: dict, market_conditions: dict) -> dict:
    # Step 1: Analyze market exposure
    step1_prompt = """Analyze the market risk exposure of this portfolio:
- Calculate beta and volatility
- Identify correlation risks
- Assess market timing risks

Portfolio:
""" + json.dumps(portfolio_data, indent=2)
    
    step1_result = chat(step1_prompt)
    
    # Step 2: Analyze concentration risk
    step2_prompt = """Identify concentration risks in this portfolio:
- Sector concentration
- Single stock exposure
- Geographic concentration
- Asset class concentration

Portfolio:
""" + json.dumps(portfolio_data, indent=2)
    
    step2_result = chat(step2_prompt)
    
    # Step 3: Comprehensive assessment
    prompt = f"""You are a risk assessment expert. Perform comprehensive portfolio risk assessment:

Portfolio:
{json.dumps(portfolio_data, indent=2)}

Market Conditions:
{json.dumps(market_conditions, indent=2)}

Previous analysis findings:
Market Risk Assessment: {step1_result}
Concentration Risk Assessment: {step2_result}

Now provide:
1. Liquidity risk assessment
2. Counterparty risk analysis
3. Currency risk (if applicable)
4. Interest rate risk exposure
5. Overall portfolio risk score (0-100)
6. Key Risk Drivers
7. Actionable Recommendations

Return detailed risk breakdown with specific insights and recommendations."""
    result = chat(prompt)
    return {
        "agent": "RiskAssessment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assessment_type": "portfolio",
        "thinking_steps": [
            {"step": 1, "analysis": "Market Risk Analysis", "details": step1_result[:500]},
            {"step": 2, "analysis": "Concentration Risk Analysis", "details": step2_result[:500]},
            {"step": 3, "analysis": "Comprehensive Assessment", "details": result[:500]},
        ],
        "risk_analysis": f"**Market Risk Analysis:**\n{step1_result}\n\n**Concentration Risk Analysis:**\n{step2_result}\n\n**Comprehensive Assessment:**\n{result}",
        "complete": True,
    }


def detect_fraud_risk(
    transaction_history: list[dict[str, Any]],
    portfolio_data: dict[str, Any],
    ml_pre_scores: list[dict[str, Any]] | None = None,
) -> dict:
    ml_summary_lines: list[str] = []
    high_risk_txns = []
    
    if ml_pre_scores:
        for index, result in enumerate(ml_pre_scores):
            score = result.get('final_score', result.get('risk_score', 0))
            label = result.get('risk_label', '?')
            ml_summary_lines.append(
                f"  Txn {index + 1}: score={score}/100 "
                f"label={label} "
                f"flags=[{', '.join(result.get('flags', []))}]"
            )
            if score and score >= 55:
                high_risk_txns.append((index, score, label))
    else:
        engine = get_risk_engine()
        if engine:
            for index, txn in enumerate(transaction_history[:20]):
                try:
                    result = engine.score(txn)
                    score = result['final_score']
                    label = result['risk_label']
                    ml_summary_lines.append(
                        f"  Txn {index + 1}: score={score}/100 "
                        f"label={label} method={result['method']} "
                        f"flags=[{', '.join(result['flags'])}]"
                    )
                    if score >= 55:
                        high_risk_txns.append((index, score, label))
                except Exception:
                    ml_summary_lines.append(f"  Txn {index + 1}: ML scoring failed")

    ml_section = ""
    if ml_summary_lines:
        ml_section = (
            "\n\n── ML Pre-Screening Results (Rules + GradientBoosting + IsolationForest) ──\n"
            + "\n".join(ml_summary_lines)
            + "\n\nUse these ML scores as your baseline. Add expert analysis on top."
        )
    
    # Step 1: Analyze high-risk transactions
    step1_result = ""
    if high_risk_txns:
        hrt_list = ", ".join([f"Txn {idx+1} (score: {score}/100, {label})" for idx, score, label in high_risk_txns])
        step1_prompt = f"""Analyze these high-risk transactions for fraud indicators:
{hrt_list}

Transactions:
{json.dumps([transaction_history[i] for i, _, _ in high_risk_txns[:5]], indent=2)}

Identify specific fraud patterns, velocity concerns, and behavioral anomalies."""
        step1_result = chat(step1_prompt)
    
    # Step 2: Portfolio-level analysis
    step2_prompt = f"""Perform portfolio-level fraud risk assessment:

Portfolio Data:
{json.dumps(portfolio_data, indent=2)}

Assess for:
- Unusual account activity patterns
- Geographic inconsistencies
- Account takeover signs
- Layering/structuring patterns
- Potential money laundering"""
    
    step2_result = chat(step2_prompt)
    
    # Step 3: Comprehensive assessment
    prompt = (
        "You are a financial fraud detection expert. Provide comprehensive fraud risk assessment:\n\n"
        f"Transaction History:\n{json.dumps(transaction_history[:10], indent=2)}\n\n"
        f"Portfolio Data:\n{json.dumps(portfolio_data, indent=2)}"
        f"{ml_section}\n\n"
        f"High-Risk Transaction Analysis:\n{step1_result}\n\n"
        f"Portfolio-Level Analysis:\n{step2_result}\n\n"
        "Provide:\n"
        "1. Overall fraud risk assessment\n"
        "2. Key risk drivers\n"
        "3. Specific transaction alerts\n"
        "4. Recommended SAR filing if warranted\n"
        "5. Immediate action items"
    )
    response = chat(prompt)
    
    return {
        "agent": "RiskDetector",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_type": "fraud_risk",
        "thinking_steps": [
            {"step": 1, "analysis": "High-Risk Transaction Analysis", "details": step1_result[:300]} if step1_result else None,
            {"step": 2, "analysis": "Portfolio-Level Analysis", "details": step2_result[:300]},
            {"step": 3, "analysis": "Comprehensive Assessment", "details": response[:300]},
        ],
        "assessment": f"**Transaction-Level Analysis:**\n{step1_result}\n\n**Portfolio Analysis:**\n{step2_result}\n\n**Comprehensive Assessment:**\n{response or 'Fraud analysis unavailable.'}",
    }


def assess_market_risk(portfolio_data: dict[str, Any], market_conditions: dict[str, Any]) -> dict:
    prompt = (
        "You are a market risk analyst. Assess portfolio risk in current "
        "market conditions:\n\n"
        f"Portfolio:\n{json.dumps(portfolio_data, indent=2)}\n\n"
        f"Market Conditions:\n{json.dumps(market_conditions, indent=2)}\n\n"
        "Provide:\n"
        "1. Market risk exposure assessment\n"
        "2. Sector-specific risks\n"
        "3. Systemic risk analysis\n"
        "4. Hedging recommendations\n"
        "5. Protective measures"
    )
    response = chat(prompt)
    return {
        "agent": "RiskDetector",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_type": "market_risk",
        "assessment": response or "Market risk assessment unavailable.",
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
            "Quick risk assessment (2-3 sentences):\n"
            f"{portfolio_summary}\n"
            "Key risks? Recommendation?\n"
            f"{ml_summary}"
        )
        recommendation = chat(prompt)
        crew_output = (
            "## ⚡ Quick Recommendation\n\n"
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
            "agents_used": 1,
            "recommendation_type": "quick",
            "rate_limited": False,
        }
    except Exception as exc:
        if is_rate_limit_error(exc):
            fallback = (
                "⚠️ **Rate Limit Reached**\n\n"
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
            }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "portfolio_id": portfolio_data.get("id"),
            "crew_output": f"❌ Quick recommendation failed: {str(exc)[:200]}",
            "agents_used": 0,
            "recommendation_type": "quick",
            "error": str(exc),
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

    return {
        "agent": "risk",
        "mode": mode,
        "summary": " ".join(findings),
        "findings": findings,
        "scored_transactions": scored,
    }


class RiskAssessmentAgent:
    AGENT_DOMAIN = "risk_assessment"

    def assess_portfolio_risk(self, portfolio_data: dict, market_conditions: dict) -> dict:
        return assess_portfolio_risk(portfolio_data, market_conditions)

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
