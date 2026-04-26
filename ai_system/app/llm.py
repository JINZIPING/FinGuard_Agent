"""OpenAI adapter with legacy-style retry and error semantics."""

from __future__ import annotations

import os
import time

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional at import time
    OpenAI = None

try:
    from langsmith import traceable
    from langsmith.wrappers import wrap_openai
except ImportError:  # pragma: no cover - tracing is optional at import time

    def traceable(*_: object, **__: object) -> object:
        def decorator(func: object) -> object:
            return func

        return decorator

    def wrap_openai(client: object) -> object:
        return client


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


def _configured_api_keys() -> list[tuple[str, str]]:
    keys = [
        ("primary", os.getenv("OPENAI_API_KEY")),
        ("backup", os.getenv("OPENAI_API_KEY_BACKUP")),
    ]
    return [(label, key) for label, key in keys if key]


@traceable(name="openai_chat", run_type="llm")
def chat(message: str, system_prompt: str | None = None, max_retries: int = 3) -> str:
    api_keys = _configured_api_keys()
    if not api_keys:
        raise RuntimeError(
            "❌ LLM Configuration Error: OPENAI_API_KEY environment variable is not set.\n"
            "Please set OPENAI_API_KEY before calling ai_system analysis endpoints. "
            "Optionally set OPENAI_API_KEY_BACKUP for rate-limit failover."
        )
    if OpenAI is None:
        raise RuntimeError(
            "❌ LLM Configuration Error: openai package is not installed.\n"
            "Install ai_system dependencies before calling ai_system analysis endpoints."
        )

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "medium")

    messages = [{"role": "user", "content": message}]
    last_rate_limit_error: Exception | None = None

    for key_index, (_, api_key) in enumerate(api_keys):
        client = wrap_openai(OpenAI(api_key=api_key))

        for attempt in range(max_retries):
            try:
                create_kwargs: dict = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": 2048,
                }
                if system_prompt:
                    create_kwargs["system"] = system_prompt
                # o-series models (o1, o3, o4, …) support reasoning; gpt-4o-mini does not
                if model.startswith("o") and model[1:2].isdigit():
                    create_kwargs["reasoning"] = {
                        "type": "enabled",
                        "budget_tokens": 1000,
                    }
                response = client.chat.completions.create(**create_kwargs)
                return response.choices[0].message.content
            except Exception as exc:
                if not is_rate_limit_error(exc):
                    raise RuntimeError(_format_chat_error(exc)) from exc

                last_rate_limit_error = exc
                has_backup_key = key_index < len(api_keys) - 1
                if has_backup_key:
                    break
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(_format_chat_error(exc)) from exc

    if last_rate_limit_error is not None:
        raise RuntimeError(_format_chat_error(last_rate_limit_error)) from last_rate_limit_error
    raise RuntimeError("❌ LLM Call Failed: exhausted retries without a response")
