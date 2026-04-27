"""Portfolio analysis logic aligned to the legacy prompts."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.llm import chat


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _portfolio_contract(audience: str = "analyst") -> str:
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


def _portfolio_metrics(portfolio: dict, transactions: list[dict] | None = None) -> dict:
    assets = portfolio.get("assets", []) or []
    transactions = transactions or []
    total_value = float(portfolio.get("total_value") or 0)
    cash_balance = float(portfolio.get("cash_balance") or 0)
    cash_ratio = (cash_balance / total_value) if total_value else 0.0
    asset_symbols = {asset.get("symbol") for asset in assets if asset.get("symbol")}
    txn_symbols = {txn.get("symbol") for txn in transactions if txn.get("symbol")}
    unique_symbols = len(asset_symbols or txn_symbols)
    return {
        "total_value": total_value,
        "cash_balance": cash_balance,
        "cash_ratio": cash_ratio,
        "asset_count": len(assets),
        "unique_symbols": unique_symbols,
        "transaction_count": len(transactions),
        "is_funded": total_value > 0,
    }


def _portfolio_findings(metrics: dict) -> list[str]:
    findings: list[str] = []
    if not metrics["is_funded"]:
        findings.append(
            "Portfolio has no funded value yet, so allocation analysis is preliminary."
        )
    if metrics["unique_symbols"] <= 2 and metrics["transaction_count"]:
        findings.append(
            "Portfolio diversification appears thin based on recent symbol activity."
        )
    if metrics["asset_count"] <= 2 and metrics["is_funded"]:
        findings.append("Portfolio has a small number of holdings.")
    if metrics["cash_ratio"] > 0.35:
        findings.append("Cash allocation is high relative to portfolio value.")
    elif 0 < metrics["cash_ratio"] < 0.05:
        findings.append("Cash buffer is thin for near-term flexibility.")
    return findings


def _severity_from_metrics(metrics: dict, findings: list[str], text: str = "") -> str:
    if not metrics["is_funded"]:
        return "unknown"
    if metrics["unique_symbols"] <= 1 and metrics["cash_ratio"] < 0.05:
        return "high"
    if len(findings) >= 2:
        return "medium"
    return risk_severity(text=text) if text else "low"


def _actions_for_severity(severity: str) -> list[str]:
    if severity in {"critical", "high"}:
        return [
            "Review concentration and liquidity before adding exposure.",
            "Consider diversifying across additional holdings or sectors.",
            "Run a full portfolio analysis before major trading decisions.",
        ]
    if severity == "medium":
        return [
            "Document concentration, cash, and diversification observations.",
            "Monitor whether new transactions increase portfolio imbalance.",
        ]
    if severity == "unknown":
        return ["Fund or enrich the portfolio data before relying on allocation analysis."]
    return ["Continue routine portfolio monitoring."]


def analyze_portfolio(portfolio: dict) -> dict:
    metrics = _portfolio_metrics(portfolio)
    deterministic_findings = _portfolio_findings(metrics)
    prompt = (
        "You are a professional portfolio analyst.\n\n"
        f"Portfolio Data:\n{json.dumps(portfolio, indent=2)}\n\n"
        f"Deterministic Prechecks:\n{json.dumps(metrics, indent=2)}\n"
        f"Precheck Findings:\n{json.dumps(deterministic_findings, indent=2)}\n\n"
        f"{_portfolio_contract('analyst')}\n"
        "Focus on allocation, diversification, liquidity, and practical recommendations."
    )
    response = chat(prompt)
    analysis = response or "Portfolio analysis unavailable."
    severity = _severity_from_metrics(metrics, deterministic_findings, analysis)
    return {
        "agent": "PortfolioAnalyzer",
        "timestamp": _timestamp(),
        "analysis": analysis,
        "metrics": metrics,
        "structured_output": build_structured_output(
            summary=_summary_from_text(analysis, "Portfolio analysis unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=deterministic_findings
            or [
                f"Assets reviewed: {metrics['asset_count']}",
                f"Cash ratio: {metrics['cash_ratio']:.1%}"
                if metrics["is_funded"]
                else "Cash ratio unavailable for unfunded portfolio.",
            ],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Reassess after material deposits, withdrawals, or allocation changes."],
            raw_text=analysis,
        ),
    }


def rebalance_portfolio(portfolio_data: dict, target_allocation: dict[str, float]) -> dict:
    prompt = (
        "You are a portfolio rebalancing expert. Based on this portfolio and target allocation:\n\n"
        f"Current Portfolio:\n{json.dumps(portfolio_data, indent=2)}\n\n"
        f"Target Allocation:\n{json.dumps(target_allocation, indent=2)}\n\n"
        f"{_portfolio_contract('analyst')}\n"
        "Compare current vs target allocation, identify priority trades, and note tax or timing considerations."
    )
    response = chat(prompt)
    plan = response or "Rebalancing plan unavailable."
    severity = risk_severity(text=plan)
    return {
        "agent": "PortfolioAnalyzer",
        "timestamp": _timestamp(),
        "action": "rebalance",
        "plan": plan,
        "structured_output": build_structured_output(
            summary=_summary_from_text(plan, "Rebalancing plan unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=[
                f"Target allocation entries: {len(target_allocation)}",
                f"Current assets: {len(portfolio_data.get('assets', []) or [])}",
            ],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Confirm tax and liquidity impact before trade execution."],
            raw_text=plan,
        ),
    }


def invoke(portfolio: dict, transactions: list[dict], mode: str = "quick") -> dict:
    if mode == "full":
        result = analyze_portfolio(portfolio)
        return {
            "agent": "portfolio",
            "mode": mode,
            "summary": result["analysis"],
            "analysis": result["analysis"],
            "findings": [result["analysis"]],
            "metrics": result["metrics"],
            "structured_output": result["structured_output"],
        }

    metrics = _portfolio_metrics(portfolio, transactions)
    findings = _portfolio_findings(metrics)
    if not findings:
        findings.append("Quick portfolio screen looks balanced at a high level.")
    severity = _severity_from_metrics(metrics, findings)
    summary = " ".join(findings)

    return {
        "agent": "portfolio",
        "mode": mode,
        "summary": summary,
        "findings": findings,
        "metrics": metrics,
        "structured_output": build_structured_output(
            summary=summary,
            severity=severity,
            confidence="high",
            key_factors=findings,
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Run full analysis when allocation or transaction patterns change."],
            raw_text=summary,
        ),
    }


class PortfolioAnalysisAgent:
    AGENT_DOMAIN = "portfolio_analysis"

    def analyze_portfolio(self, portfolio_data: dict) -> dict:
        return analyze_portfolio(portfolio_data)

    def rebalance_portfolio(self, portfolio_data: dict, target_allocation: dict[str, float]) -> dict:
        return rebalance_portfolio(portfolio_data, target_allocation)

