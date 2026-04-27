"""Market sentiment and recommendation logic aligned to the legacy prompts."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.llm import chat, is_rate_limit_error


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _market_contract(audience: str = "analyst") -> str:
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


def _data_basis(symbols: list[str], news_context: str | None = None) -> dict:
    return {
        "symbols": symbols,
        "source": "model_generated_market_context",
        "live_market_data": False,
        "external_context_supplied": bool(news_context),
        "note": "No live market data feed is wired into this agent.",
    }


def _confidence(news_context: str | None = None, rate_limited: bool = False) -> str:
    if rate_limited:
        return "low"
    return "medium" if news_context else "low"


def _actions_for_market(severity: str) -> list[str]:
    if severity in {"critical", "high"}:
        return [
            "Validate with live quotes and news before acting.",
            "Review position size and downside exposure.",
            "Escalate material portfolio-impact decisions for human approval.",
        ]
    if severity == "medium":
        return [
            "Cross-check the model output against current market data.",
            "Monitor catalysts and portfolio exposure before trading.",
        ]
    return ["Use this as context only and confirm with live market data."]


def analyze_sentiment(symbols: list[str], news_context: str | None = None) -> dict:
    clean_symbols = [symbol.upper() for symbol in symbols if symbol]
    context_suffix = f"\nContext: {news_context}" if news_context else ""
    prompt = (
        f"You are a market sentiment analyst. Provide sentiment analysis for: {', '.join(clean_symbols)}\n"
        f"{context_suffix}\n\n"
        f"{_market_contract('analyst')}\n"
        "Be symbol-specific. State that this is model-generated context unless supplied context contains current market data."
    )
    rate_limited = False
    try:
        sentiment_analysis = chat(prompt)
    except Exception as exc:
        if is_rate_limit_error(exc):
            rate_limited = True
            sentiment_analysis = (
                "?? Market sentiment is temporarily rate limited. "
                "Please wait 30-60 seconds and retry."
            )
        else:
            sentiment_analysis = f"Sentiment analysis unavailable: {str(exc)[:200]}"
    severity = risk_severity(text=sentiment_analysis)
    data_basis = _data_basis(clean_symbols, news_context)
    return {
        "agent": "MarketIntelligence",
        "timestamp": _timestamp(),
        "symbols": clean_symbols,
        "sentiment_analysis": sentiment_analysis,
        "rate_limited": rate_limited,
        "data_basis": data_basis,
        "structured_output": build_structured_output(
            summary=_summary_from_text(
                sentiment_analysis, "Market sentiment unavailable."
            ),
            severity=severity,
            confidence=_confidence(news_context, rate_limited),
            key_factors=[
                f"Symbols reviewed: {', '.join(clean_symbols) or 'none'}",
                "External context supplied: " + ("yes" if news_context else "no"),
                "Live market data wired: no",
            ],
            recommended_actions=_actions_for_market(severity),
            follow_up=["Refresh with live market data before investment action."],
            raw_text=sentiment_analysis,
        ),
    }


def analyze_market_sentiment(symbols: list[str], news_context: str = "") -> dict:
    return analyze_sentiment(symbols, news_context or None)


def generate_recommendation(
    symbol: str, portfolio_size: float, risk_profile: str
) -> dict:
    clean_symbol = symbol.upper()
    prompt = (
        f"You are a professional investment advisor. Provide a recommendation for {clean_symbol}:\n\n"
        f"Portfolio Size: ${portfolio_size:,.2f}\n"
        f"Risk Profile: {risk_profile}\n\n"
        f"{_market_contract('analyst')}\n"
        "Include Buy/Hold/Sell posture, position sizing guidance, key catalysts, and risk controls. "
        "State that live prices/news must be checked before execution."
    )
    rate_limited = False
    try:
        recommendation = chat(prompt)
    except Exception as exc:
        if is_rate_limit_error(exc):
            rate_limited = True
            recommendation = (
                "?? Recommendation engine is temporarily rate limited. "
                "Please wait 30-60 seconds and retry."
            )
        else:
            recommendation = (
                f"Recommendation unavailable for {clean_symbol}: {str(exc)[:200]}"
            )
    severity = risk_severity(text=recommendation)
    data_basis = _data_basis([clean_symbol])
    return {
        "agent": "MarketIntelligence",
        "timestamp": _timestamp(),
        "symbol": clean_symbol,
        "recommendation": recommendation,
        "rate_limited": rate_limited,
        "data_basis": data_basis,
        "structured_output": build_structured_output(
            summary=_summary_from_text(
                recommendation, f"Recommendation unavailable for {clean_symbol}."
            ),
            severity=severity,
            confidence=_confidence(rate_limited=rate_limited),
            key_factors=[
                f"Symbol reviewed: {clean_symbol}",
                f"Portfolio size: ${portfolio_size:,.2f}",
                f"Risk profile: {risk_profile}",
            ],
            recommended_actions=_actions_for_market(severity),
            follow_up=["Confirm live market data, customer suitability, and risk limits before execution."],
            raw_text=recommendation,
        ),
    }


def generate_investment_recommendation(
    symbol: str, portfolio_size: float, risk_profile: str
) -> dict:
    return generate_recommendation(symbol, portfolio_size, risk_profile)


def quick_market_sentiment(symbols: list[str], news_context: str | None = None) -> dict:
    return analyze_sentiment(symbols, news_context)


def quick_recommendation(symbol: str, portfolio_size: float, risk_profile: str) -> dict:
    return generate_recommendation(symbol, portfolio_size, risk_profile)


class MarketIntelligenceAgent:
    AGENT_DOMAIN = "market_intelligence"

    def analyze_market_sentiment(
        self, symbols: list[str], news_context: str = ""
    ) -> dict:
        return analyze_market_sentiment(symbols, news_context)

    def generate_investment_recommendation(
        self, symbol: str, portfolio_size: float, risk_profile: str
    ) -> dict:
        return generate_investment_recommendation(symbol, portfolio_size, risk_profile)

