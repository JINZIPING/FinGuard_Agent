"""Groq LLM adapter with retry and error semantics."""

from __future__ import annotations

import os
import re
import time

try:
    from groq import Groq
except ImportError:  # pragma: no cover
    Groq = None

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover

    def traceable(*_: object, **__: object) -> object:
        def decorator(func: object) -> object:
            return func
        return decorator


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

    if "401" in error_msg or "Unauthorized" in error_msg or "invalid api key" in error_msg.lower():
        return (
            "❌ LLM Authentication Failed: Invalid or expired Groq API key\n"
            f"Details: {error_msg}\n"
            "Fix: Get a key at https://console.groq.com and set GROQ_API_KEY"
        )
    if is_rate_limit_error(error_msg):
        return (
            "⏳ LLM Rate Limited: Too many requests to Groq API\n"
            f"Details: {error_msg}\n"
            "Fix: Wait 5-10 seconds and retry."
        )
    if "503" in error_msg or "Service unavailable" in error_msg:
        return (
            "🚨 LLM Service Unavailable: Groq API is temporarily down\n"
            f"Details: {error_msg}\n"
            "Fix: Check https://status.groq.com and retry in a moment"
        )
    return (
        f"❌ LLM Call Failed ({error_type}):\n"
        f"{error_msg}\n"
        "Fix: Check GROQ_API_KEY, model name, and https://console.groq.com"
    )


@traceable(name="groq_chat", run_type="llm")
def chat(message: str, system_prompt: str | None = None, max_retries: int = 3) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "❌ LLM Configuration Error: GROQ_API_KEY is not set.\n"
            "Get a free key at https://console.groq.com and set GROQ_API_KEY."
        )
    if Groq is None:
        raise RuntimeError(
            "❌ LLM Configuration Error: groq package is not installed.\n"
            "Run: pip install groq"
        )

    client = Groq(api_key=api_key)
    model = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
            )
            raw = response.choices[0].message.content
            return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        except Exception as exc:
            if is_rate_limit_error(exc) and attempt < max_retries - 1:
                time.sleep(5 * (2 ** attempt))
                continue
            raise RuntimeError(_format_chat_error(exc)) from exc

    raise RuntimeError("❌ LLM Call Failed: exhausted retries without a response")
