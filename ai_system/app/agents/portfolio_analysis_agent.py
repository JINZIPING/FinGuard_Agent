"""Portfolio analysis logic aligned to the legacy prompts."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ai_system.app.llm import chat


def analyze_portfolio(portfolio: dict) -> dict:
    # Step 1: Allocation Analysis
    step1_prompt = (
        "Analyze the asset allocation of this portfolio:\n"
        "1. Current allocation breakdown\n"
        "2. Comparison to industry benchmarks\n"
        "3. Concentration risks\n\n"
        f"Portfolio Data:\n{json.dumps(portfolio, indent=2)}"
    )
    step1_response = chat(step1_prompt)
    
    # Step 2: Diversification Assessment
    step2_prompt = (
        "Evaluate diversification of this portfolio:\n"
        "1. Sector diversification score\n"
        "2. Asset class diversification\n"
        "3. Geographic diversification\n"
        "4. Correlation analysis between holdings\n\n"
        f"Portfolio Data:\n{json.dumps(portfolio, indent=2)}"
    )
    step2_response = chat(step2_prompt)
    
    # Step 3: Performance & Risk Analysis
    step3_prompt = (
        "Assess performance and risk profile:\n"
        "1. Historical performance vs benchmarks\n"
        "2. Risk metrics (Sharpe ratio, Beta)\n"
        "3. Volatility analysis\n"
        "4. Downside risk assessment\n\n"
        f"Portfolio Data:\n{json.dumps(portfolio, indent=2)}"
    )
    step3_response = chat(step3_prompt)
    
    # Step 4: Comprehensive recommendations
    prompt = (
        "You are a professional portfolio analyst. Provide comprehensive portfolio analysis:\n\n"
        f"Asset Allocation Analysis:\n{step1_response}\n\n"
        f"Diversification Assessment:\n{step2_response}\n\n"
        f"Performance & Risk Analysis:\n{step3_response}\n\n"
        "Provide actionable recommendations:\n"
        "1. Rebalancing suggestions\n"
        "2. Risk mitigation strategies\n"
        "3. Performance optimization opportunities\n"
        "4. Specific buy/sell recommendations"
    )
    response = chat(prompt)
    
    return {
        "agent": "PortfolioAnalyzer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "thinking_steps": [
            {"step": 1, "analysis": "Asset Allocation Analysis", "details": step1_response[:400]},
            {"step": 2, "analysis": "Diversification Assessment", "details": step2_response[:400]},
            {"step": 3, "analysis": "Performance & Risk", "details": step3_response[:400]},
            {"step": 4, "analysis": "Recommendations", "details": response[:400]},
        ],
        "analysis": f"**Asset Allocation:**\n{step1_response}\n\n**Diversification:**\n{step2_response}\n\n**Performance & Risk:**\n{step3_response}\n\n**Recommendations:**\n{response or 'Portfolio analysis unavailable.'}",
    }


def rebalance_portfolio(portfolio_data: dict, target_allocation: dict[str, float]) -> dict:
    prompt = (
        "You are a portfolio rebalancing expert. Based on this portfolio and target allocation:\n\n"
        f"Current Portfolio:\n{json.dumps(portfolio_data, indent=2)}\n\n"
        f"Target Allocation:\n{json.dumps(target_allocation, indent=2)}\n\n"
        "Generate a detailed rebalancing plan with:\n"
        "1. Current vs target allocation comparison\n"
        "2. Specific trades to execute\n"
        "3. Expected impact on returns\n"
        "4. Tax implications to consider\n"
        "5. Implementation timeline"
    )
    response = chat(prompt)
    return {
        "agent": "PortfolioAnalyzer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "rebalance",
        "plan": response or "Rebalancing plan unavailable.",
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
        }

    total_value = float(portfolio.get("total_value") or 0)
    cash_balance = float(portfolio.get("cash_balance") or 0)
    unique_symbols = len(
        {txn.get("symbol") for txn in transactions if txn.get("symbol")}
    )
    cash_ratio = (cash_balance / total_value) if total_value else 0.0

    findings = []
    if total_value == 0:
        findings.append(
            "Portfolio has no funded value yet, so allocation analysis is preliminary."
        )
    if unique_symbols <= 2 and transactions:
        findings.append(
            "Portfolio diversification appears thin based on recent symbol activity."
        )
    if cash_ratio > 0.35:
        findings.append("Cash allocation is high relative to portfolio value.")
    elif 0 < cash_ratio < 0.05:
        findings.append("Cash buffer is thin for near-term flexibility.")
    if not findings:
        findings.append("Quick portfolio screen looks balanced at a high level.")

    return {
        "agent": "portfolio",
        "mode": mode,
        "summary": " ".join(findings),
        "findings": findings,
    }


class PortfolioAnalysisAgent:
    AGENT_DOMAIN = "portfolio_analysis"

    def analyze_portfolio(self, portfolio_data: dict) -> dict:
        return analyze_portfolio(portfolio_data)

    def rebalance_portfolio(self, portfolio_data: dict, target_allocation: dict[str, float]) -> dict:
        return rebalance_portfolio(portfolio_data, target_allocation)
