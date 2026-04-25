"""Deterministic mock responses for demos, tests, and offline development."""

from __future__ import annotations

import re


INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "reveal your system prompt",
    "show the system prompt",
    "developer message",
    "api key",
    "secret",
    "tool output",
    "bypass safety",
    "jailbreak",
)


def _mentions_prompt_injection(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(pattern in lowered for pattern in INJECTION_PATTERNS)


def _extract_symbols(prompt: str) -> list[str]:
    matches = re.findall(r"\b[A-Z]{2,5}\b", prompt)
    seen: list[str] = []
    for match in matches:
        if match not in seen:
            seen.append(match)
    return seen[:5]


def generate_mock_response(message: str, system_prompt: str | None = None) -> str:
    prompt = "\n".join(part for part in (system_prompt, message) if part)
    symbols = _extract_symbols(prompt)

    if _mentions_prompt_injection(prompt):
        return (
            "Mock safeguard response: instruction-tampering language was detected and ignored. "
            "Requests to reveal the system prompt or secrets are refused. "
            "Continue with portfolio risk analysis using only the supplied business context."
        )

    lowered = prompt.lower()

    if "market sentiment analyst" in lowered or "sentiment analysis for" in lowered:
        joined = ", ".join(symbols or ["the requested symbols"])
        return (
            f"Mock market sentiment for {joined}: sentiment is cautiously positive. "
            "Momentum is constructive, but analysts should watch rate-sensitive volatility and earnings guidance."
        )

    if "professional investment advisor" in lowered or "provide a recommendation for" in lowered:
        symbol = symbols[0] if symbols else "the selected symbol"
        return (
            f"Recommendation for {symbol}: HOLD with selective accumulation on weakness. "
            "Suggested position size is 3-5% of portfolio value, with disciplined risk limits and catalyst monitoring."
        )

    if "transaction was scored by our automated system with a borderline result" in lowered:
        return (
            "The transaction sits in a review band because its amount, timing, and counterparty context are unusual "
            "relative to baseline behavior. Recommended action: HOLD_FOR_REVIEW while validating customer intent and linked activity."
        )

    if "score the risk level of this transaction" in lowered:
        return (
            "Mock transaction risk review: score 78/100, label high. "
            "Primary drivers are amount deviation, unusual geography, and rapid transaction velocity. "
            "Recommended action: ESCALATE."
        )

    if "risk assessment expert" in lowered and "portfolio" in lowered:
        return (
            "Portfolio risk assessment: overall risk is medium-high due to concentration in correlated growth assets, "
            "limited cash buffer, and elevated transaction volatility. Prioritize diversification, liquidity review, and scenario testing."
        )

    if "financial fraud detection expert" in lowered:
        return (
            "Fraud review: repeated elevated transaction scores, velocity signals, and cross-border behavior justify analyst review. "
            "Open a monitoring case, validate counterparties, and compare against prior customer patterns."
        )

    if "professional portfolio analyst" in lowered:
        return (
            "Portfolio analysis: diversification is moderate, but exposure is clustered in a few symbols and sectors. "
            "Strengthen risk balance by trimming concentration, preserving a larger cash buffer, and stress-testing downside scenarios."
        )

    if "summarize this analysis" in lowered:
        return (
            "Executive summary: the portfolio shows manageable risk but warrants closer review because transaction behavior and allocation "
            "concentration create escalation pressure. Recommended actions: validate flagged activity, document rationale, and monitor for recurrence."
        )

    if "explain this transaction risk score" in lowered:
        return (
            "This score means the transaction is materially more unusual than the customer's expected pattern. "
            "The main drivers are size, timing, and contextual red flags, so the safest next step is human review before closure."
        )

    if "explain this financial alert" in lowered:
        return (
            "This alert was generated because the system found behavior that differs from expected account activity. "
            "It does not prove wrongdoing, but it does require review and documentation before the case can be cleared."
        )

    return (
        "Mock analysis response: the supplied financial context indicates moderate operational risk with clear human-review checkpoints. "
        "Use this output for testing, demos, and trace validation only."
    )
