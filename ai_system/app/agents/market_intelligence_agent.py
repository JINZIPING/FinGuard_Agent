"""Market sentiment and recommendation logic aligned to the legacy prompts."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_system.app.llm import chat, get_last_thinking, is_rate_limit_error


def analyze_sentiment(symbols: list[str], news_context: str | None = None) -> dict:
    clean_symbols = [symbol.upper() for symbol in symbols if symbol]
    context_suffix = f"\nContext: {news_context}" if news_context else ""
    prompt = (
        f"You are a market sentiment analyst. Provide sentiment analysis for: {', '.join(clean_symbols)}\n"
        f"{context_suffix}\n\n"
        "Provide:\n"
        "1. Sentiment score for each symbol (-1 to 1)\n"
        "2. Key sentiment drivers\n"
        "3. Confidence level\n"
        "4. Short-term outlook (1-4 weeks)\n"
        "5. Long-term outlook (3-6 months)"
    )
    rate_limited = False
    thinking = ""
    try:
        sentiment_analysis = chat(prompt)
        thinking = get_last_thinking()
    except Exception as exc:
        if is_rate_limit_error(exc):
            rate_limited = True
            sentiment_analysis = (
                "⚠️ Market sentiment is temporarily rate limited. "
                "Please wait 30-60 seconds and retry."
            )
        else:
            sentiment_analysis = f"Sentiment analysis unavailable: {str(exc)[:200]}"
    result = {
        "agent": "MarketIntelligence",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols": clean_symbols,
        "sentiment_analysis": sentiment_analysis,
        "rate_limited": rate_limited,
    }
    if thinking:
        result["thinking"] = thinking
    return result


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
        "Provide:\n"
        "1. Buy/Hold/Sell recommendation\n"
        "2. Target entry/exit prices\n"
        "3. Position sizing (% of portfolio)\n"
        "4. Risk-reward ratio\n"
        "5. Key catalysts to watch\n"
        "6. Alternative positions to consider"
    )
    rate_limited = False
    try:
        recommendation = chat(prompt)
    except Exception as exc:
        if is_rate_limit_error(exc):
            rate_limited = True
            recommendation = (
                "⚠️ Recommendation engine is temporarily rate limited. "
                "Please wait 30-60 seconds and retry."
            )
        else:
            recommendation = (
                f"Recommendation unavailable for {clean_symbol}: {str(exc)[:200]}"
            )
    return {
        "agent": "MarketIntelligence",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": clean_symbol,
        "recommendation": recommendation,
        "rate_limited": rate_limited,
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
