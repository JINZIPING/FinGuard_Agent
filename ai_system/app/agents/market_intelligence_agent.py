"""Market sentiment and recommendation logic aligned to the legacy prompts."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.llm import chat, is_rate_limit_error

DETAIL_LEVELS = {"short", "detailed"}
MARKET_TEMPERATURE = 0.0
SEVERITY_LEVELS = {"low", "medium", "high", "critical", "unknown"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_detail_level(detail_level: str | None) -> str:
    level = (detail_level or "short").strip().lower()
    return level if level in DETAIL_LEVELS else "short"


def _sentiment_base_contract(audience: str = "analyst", detail_level: str = "short") -> str:
    level = _normalize_detail_level(detail_level)
    return (
        "You are producing a symbol-level market sentiment signal for analysts.\n"
        "Keep the response concise and action-oriented. Use these sections only:\n"
        "Signal summary: 1-2 sentences.\n"
        "Sentiment direction: bullish, neutral, bearish, or mixed.\n"
        "Signal severity: low, medium, high, critical, or unknown.\n"
        "Signal confidence: low, medium, or high.\n"
        "Drivers: up to 3 bullets.\n"
        "Uncertainty and invalidation triggers: up to 2 bullets.\n"
        "Monitoring focus: up to 2 bullets.\n"
        f"Audience: {audience}.\n"
        f"Detail level: {level}.\n"
        "Requirements:\n"
        "- Be symbol-specific and mention each provided ticker.\n"
        "- Cite only high-level drivers; do not fabricate precise real-time prices.\n"
        "- This is context analysis only; no personalized position sizing."
    )


def _recommendation_base_contract(audience: str = "analyst", detail_level: str = "short") -> str:
    level = _normalize_detail_level(detail_level)
    return (
        "You are producing an execution-aware investment recommendation for analysts.\n"
        "Keep the response concise and action-oriented. Use these sections only:\n"
        "Recommendation summary: 1-2 sentences.\n"
        "Posture: Buy, Hold, or Sell.\n"
        "Execution risk severity: low, medium, high, critical, or unknown.\n"
        "Suitability confidence: low, medium, or high.\n"
        "Decision inputs: up to 3 bullets.\n"
        "Execution plan: up to 3 bullets.\n"
        "Risk controls and follow-up: up to 2 bullets.\n"
        f"Audience: {audience}.\n"
        f"Detail level: {level}.\n"
        "Requirements:\n"
        "- Tie guidance to provided portfolio size and risk profile.\n"
        "- Include at least one risk control (sizing discipline, stop, hedge, or escalation).\n"
        "- Avoid certainty language and avoid fabricated live prices/news.\n"
        "- Remind that live market data and customer suitability checks are required before execution."
    )


def _sentiment_detail_instructions(detail_level: str = "short") -> str:
    return (
        "Keep the response compact and practical. Limit each section to the minimum needed."
        if _normalize_detail_level(detail_level) == "short"
        else "Provide a detailed analyst-grade response with deeper rationale, scenarios, and trade-offs."
    )


def _sentiment_contract(audience: str = "analyst", detail_level: str = "short") -> str:
    return (
        f"{_sentiment_base_contract(audience, detail_level)}\n"
        f"{_sentiment_detail_instructions(detail_level)}\n"
        "Focus on sentiment direction, top drivers, and uncertainty. "
        "Avoid portfolio sizing or personalized suitability advice."
    )


def _recommendation_detail_instructions(detail_level: str = "short") -> str:
    return (
        "Keep the response compact and practical. Limit each section to the minimum needed."
        if _normalize_detail_level(detail_level) == "short"
        else "Provide a detailed analyst-grade response with deeper rationale, scenarios, and trade-offs."
    )


def _recommendation_contract(audience: str = "analyst", detail_level: str = "short") -> str:
    return (
        f"{_recommendation_base_contract(audience, detail_level)}\n"
        f"{_recommendation_detail_instructions(detail_level)}\n"
        "Include explicit posture (buy/hold/sell), sizing guidance aligned to risk profile, "
        "and concrete risk controls. Keep suitability and execution safeguards explicit."
    )


def _summary_from_text_with_limit(text: str, fallback: str, max_len: int) -> str:
    clean = " ".join((text or fallback).split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def _plain_text(value: str) -> str:
    text = value or ""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^[\-\*\u2022]\s+", "", text, flags=re.MULTILINE)
    text = " ".join(text.split())
    return text.strip()


def _extract_tagged_value(text: str, label: str) -> str | None:
    raw = text or ""
    # First pass: resilient line-by-line parse that handles markdown like "**Label:** value"
    normalized_lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    label_lower = label.lower()
    for line in normalized_lines:
        line_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", line or "")
        line_text = re.sub(r"`([^`]+)`", r"\1", line_text)
        line_text = line_text.strip()
        if not line_text:
            continue
        lower = line_text.lower()
        if lower.startswith(f"{label_lower}:"):
            return line_text.split(":", 1)[1].strip().lower()

    # Fallback: regex across full text
    pattern = rf"(?im){re.escape(label)}\s*:\s*([^\n\r]+)"
    match = re.search(pattern, raw)
    if match:
        return match.group(1).strip().lower()
    return None


def _severity_from_raw_text(text: str) -> str:
    normalized = _plain_text(text).lower()
    match = re.search(
        r"\b(?:signal severity|execution risk severity|severity)\b\s*[:\-]\s*"
        r"(low|medium|high|critical|unknown)\b",
        normalized,
    )
    if match:
        token = match.group(1).strip()
        if token in SEVERITY_LEVELS:
            return token
    extracted = (
        _extract_tagged_value(text, "Signal severity")
        or _extract_tagged_value(text, "Execution risk severity")
        or _extract_tagged_value(text, "Severity")
    )
    if extracted:
        token = extracted.split()[0].strip(".,;:()[]{}")
        if token in SEVERITY_LEVELS:
            return token
    return "unknown"


def _confidence_from_raw_text(text: str) -> str:
    normalized = _plain_text(text).lower()
    match = re.search(
        r"\b(?:signal confidence|suitability confidence|confidence)\b\s*[:\-]\s*"
        r"(low|medium|high)\b",
        normalized,
    )
    if match:
        token = match.group(1).strip()
        if token in CONFIDENCE_LEVELS:
            return token
    extracted = (
        _extract_tagged_value(text, "Signal confidence")
        or _extract_tagged_value(text, "Suitability confidence")
        or _extract_tagged_value(text, "Confidence")
    )
    if extracted:
        token = extracted.split()[0].strip(".,;:()[]{}")
        if token in CONFIDENCE_LEVELS:
            return token
    return "low"


def _data_basis(symbols: list[str], news_context: str | None = None) -> dict:
    return {
        "symbols": symbols,
        "source": "model_generated_market_context",
        "live_market_data": False,
        "external_context_supplied": bool(news_context),
        "note": "No live market data feed is wired into this agent.",
    }


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


def _short_key_factors(clean_symbols: list[str]) -> list[str]:
    return [
        f"Symbols reviewed: {', '.join(clean_symbols) or 'none'}",
        "Live market data wired: no",
    ]


def _detailed_key_factors(clean_symbols: list[str], news_context: str | None) -> list[str]:
    return [
        f"Symbols reviewed: {', '.join(clean_symbols) or 'none'}",
        "External context supplied: " + ("yes" if news_context else "no"),
        "Live market data wired: no (model-generated context)",
    ]


def _follow_up_for_level(detail_level: str) -> list[str]:
    if detail_level == "detailed":
        return [
            "Refresh with live market data before investment action.",
            "Reassess thesis if earnings, macro, or liquidity conditions materially change.",
        ]
    return ["Refresh with live market data before investment action."]


def _actions_for_level(severity: str, detail_level: str) -> list[str]:
    base_actions = _actions_for_market(severity)
    if detail_level == "detailed":
        if len(base_actions) == 1:
            return base_actions + [
                "Track upcoming catalysts that could change the thesis.",
                "Define risk limits and invalidation triggers before execution.",
            ]
        return base_actions
    return base_actions[:1]


def _stance_from_text(text: str) -> str:
    lowered = (text or "").lower()
    if any(token in lowered for token in ("bearish", "downside", "negative bias")):
        return "bearish"
    if any(token in lowered for token in ("bullish", "upside", "positive bias")):
        return "bullish"
    if "mixed" in lowered:
        return "mixed"
    return "neutral"


def _extract_bullets_under_header(text: str, header: str, max_items: int = 3) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    header_re = re.compile(
        rf"(?im)^\s*\*{{0,2}}{re.escape(header)}\*{{0,2}}\s*:\s*$"
    )
    lines = normalized.split("\n")
    in_section = False
    items: list[str] = []
    for line in lines:
        line_raw = line.rstrip()
        line_clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", line_raw).strip()
        if not in_section:
            if header_re.match(line_clean):
                in_section = True
            continue

        if not line_clean:
            if items:
                break
            continue

        # New section encountered
        if re.match(r"^\*{0,2}[A-Za-z][A-Za-z \-/&]+:\*{0,2}\s*$", line_clean):
            break

        bullet = re.sub(r"^[\-\*\u2022]\s*", "", line_clean).strip()
        if bullet:
            items.append(_plain_text(bullet))
        if len(items) >= max_items:
            break
    return items


def _market_key_factors(
    *,
    raw_text: str,
    clean_symbols: list[str],
    news_context: str | None,
    detail_level: str,
) -> list[str]:
    section_header = "Drivers"
    extracted = _extract_bullets_under_header(raw_text, section_header, max_items=3)
    if extracted:
        return extracted
    return (
        _detailed_key_factors(clean_symbols, news_context)
        if detail_level == "detailed"
        else _short_key_factors(clean_symbols)
    )


def _sentiment_structured_output(
    *,
    summary: str,
    severity: str,
    confidence: str,
    key_factors: list[str],
    recommended_actions: list[str],
    follow_up: list[str],
    raw_text: str,
) -> dict:
    return {
        "signal_summary": summary,
        "signal_strength": severity,
        "signal_confidence": confidence,
        "drivers": key_factors,
        "watch_items": recommended_actions,
        "next_checks": follow_up,
        "raw_text": raw_text,
    }


def _recommendation_structured_output(
    *,
    summary: str,
    severity: str,
    confidence: str,
    key_factors: list[str],
    recommended_actions: list[str],
    follow_up: list[str],
    raw_text: str,
) -> dict:
    return {
        "thesis_summary": summary,
        "execution_risk": severity,
        "suitability_confidence": confidence,
        "decision_inputs": key_factors,
        "execution_steps": recommended_actions,
        "controls_and_follow_up": follow_up,
        "raw_text": raw_text,
    }


def _run_market_prompt(prompt: str, rate_limit_message: str, error_prefix: str) -> tuple[str, bool]:
    rate_limited = False
    try:
        output_text = chat(prompt, temperature=MARKET_TEMPERATURE)
    except Exception as exc:
        if is_rate_limit_error(exc):
            rate_limited = True
            output_text = rate_limit_message
        else:
            output_text = f"{error_prefix}: {str(exc)[:200]}"
    return output_text, rate_limited


def _summary_limit_for_level(detail_level: str) -> int:
    return 320 if detail_level == "detailed" else 140


def analyze_sentiment(
    symbols: list[str], news_context: str | None = None, detail_level: str = "short"
) -> dict:
    clean_detail_level = _normalize_detail_level(detail_level)
    clean_symbols = [symbol.upper() for symbol in symbols if symbol]
    context_suffix = f"\nContext: {news_context}" if news_context else ""
    prompt = (
        f"You are a market sentiment analyst. Provide sentiment analysis for: {', '.join(clean_symbols)}\n"
        f"{context_suffix}\n\n"
        f"{_sentiment_contract('analyst', clean_detail_level)}\n"
        "Be symbol-specific. State that this is model-generated context unless supplied context contains current market data."
    )
    sentiment_analysis, rate_limited = _run_market_prompt(
        prompt,
        "?? Market sentiment is temporarily rate limited. Please wait 30-60 seconds and retry.",
        "Sentiment analysis unavailable",
    )
    severity = _severity_from_raw_text(sentiment_analysis)
    data_basis = _data_basis(clean_symbols, news_context)
    is_detailed = clean_detail_level == "detailed"
    confidence = _confidence_from_raw_text(sentiment_analysis)
    key_factors = _market_key_factors(
        raw_text=sentiment_analysis,
        clean_symbols=clean_symbols,
        news_context=news_context,
        detail_level=clean_detail_level,
    )
    summary = _summary_from_text_with_limit(
        _plain_text(sentiment_analysis),
        "Market sentiment unavailable.",
        _summary_limit_for_level(clean_detail_level),
    )
    recommended_actions = _actions_for_level(severity, clean_detail_level)
    follow_up = _follow_up_for_level(clean_detail_level)
    return {
        "agent": "MarketIntelligence",
        "timestamp": _timestamp(),
        "symbols": clean_symbols,
        "sentiment_analysis": sentiment_analysis,
        "rate_limited": rate_limited,
        "detail_level": clean_detail_level,
        "data_basis": data_basis,
        "structured_output": build_structured_output(
            summary=summary,
            severity=severity,
            confidence=confidence,
            key_factors=key_factors,
            recommended_actions=recommended_actions,
            follow_up=follow_up,
            raw_text=sentiment_analysis,
        )
    }


def analyze_market_sentiment(
    symbols: list[str], news_context: str = "", detail_level: str = "short"
) -> dict:
    return analyze_sentiment(symbols, news_context or None, detail_level)


def generate_recommendation(
    symbol: str, portfolio_size: float, risk_profile: str, detail_level: str = "short"
) -> dict:
    clean_detail_level = _normalize_detail_level(detail_level)
    clean_symbol = symbol.upper()
    prompt = (
        f"You are a professional investment advisor. Provide a recommendation for {clean_symbol}:\n\n"
        f"Portfolio Size: ${portfolio_size:,.2f}\n"
        f"Risk Profile: {risk_profile}\n\n"
        f"{_recommendation_contract('analyst', clean_detail_level)}\n"
        "Include Buy/Hold/Sell posture, position sizing guidance, key catalysts, and risk controls. "
        "State that live prices/news must be checked before execution."
    )
    recommendation, rate_limited = _run_market_prompt(
        prompt,
        "?? Recommendation engine is temporarily rate limited. Please wait 30-60 seconds and retry.",
        f"Recommendation unavailable for {clean_symbol}",
    )
    severity = _severity_from_raw_text(recommendation)
    data_basis = _data_basis([clean_symbol])
    is_detailed = clean_detail_level == "detailed"
    confidence = _confidence_from_raw_text(recommendation)
    key_factors = _market_key_factors(
        raw_text=recommendation,
        clean_symbols=[clean_symbol],
        news_context=None,
        detail_level=clean_detail_level,
    )
    if not key_factors:
        key_factors = [f"Symbol reviewed: {clean_symbol}"]
    summary = _summary_from_text_with_limit(
        _plain_text(recommendation),
        f"Recommendation unavailable for {clean_symbol}.",
        _summary_limit_for_level(clean_detail_level),
    )
    recommended_actions = _actions_for_level(severity, clean_detail_level)
    follow_up = (
        [
            "Confirm live market data, customer suitability, and risk limits before execution.",
            "Document assumptions and invalidation triggers before acting.",
        ]
        if is_detailed
        else ["Confirm live market data before execution."]
    )
    return {
        "agent": "MarketIntelligence",
        "timestamp": _timestamp(),
        "symbol": clean_symbol,
        "recommendation": recommendation,
        "rate_limited": rate_limited,
        "detail_level": clean_detail_level,
        "data_basis": data_basis,
        "market_view": _market_view(
            text=recommendation,
            severity=severity,
            confidence=confidence,
            key_factors=key_factors,
            detail_level=clean_detail_level,
        ),
        "structured_output": build_structured_output(
            summary=summary,
            severity=severity,
            confidence=confidence,
            key_factors=key_factors,
            recommended_actions=recommended_actions,
            follow_up=follow_up,
            raw_text=recommendation,
        )
    }


def generate_investment_recommendation(
    symbol: str, portfolio_size: float, risk_profile: str, detail_level: str = "short"
) -> dict:
    return generate_recommendation(symbol, portfolio_size, risk_profile, detail_level)


def quick_market_sentiment(
    symbols: list[str], news_context: str | None = None, detail_level: str = "short"
) -> dict:
    return analyze_sentiment(symbols, news_context, detail_level)


def quick_recommendation(
    symbol: str, portfolio_size: float, risk_profile: str, detail_level: str = "short"
) -> dict:
    return generate_recommendation(symbol, portfolio_size, risk_profile, detail_level)


class MarketIntelligenceAgent:
    AGENT_DOMAIN = "market_intelligence"

    def analyze_market_sentiment(
        self,
        symbols: list[str],
        news_context: str = "",
        detail_level: str = "short",
    ) -> dict:
        return analyze_market_sentiment(symbols, news_context, detail_level)

    def generate_investment_recommendation(
        self,
        symbol: str,
        portfolio_size: float,
        risk_profile: str,
        detail_level: str = "short",
    ) -> dict:
        return generate_investment_recommendation(
            symbol, portfolio_size, risk_profile, detail_level
        )
