"""OpenAI adapter with deterministic mock support for demos and tests."""

from __future__ import annotations

import os
import time

from ai_system.app.mock_responses import generate_mock_response

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional at import time
    OpenAI = None


def is_rate_limit_error(error: Exception | str | None) -> bool:
    text = str(error or "").lower()
    return (
        "429" in text
        or "rate limit" in text
        or "rate_limit" in text
        or "tokens per minute" in text
        or "12000" in text
    )


def _format_chat_error(error: Exception) -> str:
    error_type = type(error).__name__
    error_msg = str(error)

    if (
        "401" in error_msg
        or "Unauthorized" in error_msg
        or "invalid api key" in error_msg.lower()
    ):
        return (
            "❌ LLM Authentication Failed: Invalid or expired OpenAI API key\n"
            f"Details: {error_msg}\n"
            "Fix: Update OPENAI_API_KEY with a valid key from https://platform.openai.com/api-keys"
        )
    if is_rate_limit_error(error_msg):
        return (
            "⏳ LLM Rate Limited: Too many requests to OpenAI API (exceeded after retries)\n"
            f"Details: {error_msg}\n"
            "Fix: Wait and retry, or move to a higher OpenAI usage tier if needed."
        )
    if "503" in error_msg or "Service unavailable" in error_msg:
        return (
            "🚨 LLM Service Unavailable: OpenAI API is temporarily down\n"
            f"Details: {error_msg}\n"
            "Fix: Check https://status.openai.com and retry in a moment"
        )
    return (
        f"❌ LLM Call Failed ({error_type}):\n"
        f"{error_msg}\n"
        "Fix: Check API key, rate limits, model name, and OpenAI API status"
    )


def response_mode() -> str:
    mode = str(os.getenv("AI_RESPONSE_MODE", "live")).strip().lower()
    return mode if mode in {"live", "mock"} else "live"


def is_mock_mode() -> bool:
    return response_mode() == "mock"


def chat(message: str, system_prompt: str | None = None, max_retries: int = 3) -> str:
    if is_mock_mode():
        return generate_mock_response(message, system_prompt)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "❌ LLM Configuration Error: OPENAI_API_KEY environment variable is not set.\n"
            "Please set OPENAI_API_KEY before calling ai_system analysis endpoints."
        )
    if OpenAI is None:
        raise RuntimeError(
            "❌ LLM Configuration Error: openai package is not installed.\n"
            "Install ai_system dependencies before calling ai_system analysis endpoints."
        )

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "medium")
    instructions = system_prompt or ""
    input_items = []
    if system_prompt:
        instructions = system_prompt
    input_items.append({"role": "user", "content": message})

    for attempt in range(max_retries):
        try:
            response = client.responses.create(
                model=model,
                instructions=instructions or None,
                input=input_items,
                reasoning={"effort": reasoning_effort},
                max_output_tokens=2048,
            )
            return response.output_text
        except Exception as exc:
            if is_rate_limit_error(exc) and attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(_format_chat_error(exc)) from exc

    raise RuntimeError("❌ LLM Call Failed: exhausted retries without a response")
