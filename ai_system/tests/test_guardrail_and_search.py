from __future__ import annotations

from ai_system.app import main


def test_guardrail_blocks_dangerous_query_without_llm(monkeypatch):
    monkeypatch.setattr(
        main,
        "chat",
        lambda *_, **__: (_ for _ in ()).throw(AssertionError("LLM should not run")),
    )

    result = main.check_search_query({"query": "drop table users"})

    assert result["allowed"] is False
    assert result["blocked"] is True
    assert "disallowed" in result["reason"]


def test_guardrail_allows_finance_query_without_llm(monkeypatch):
    monkeypatch.setattr(
        main,
        "chat",
        lambda *_, **__: (_ for _ in ()).throw(AssertionError("LLM should not run")),
    )

    result = main.check_search_query({"query": "portfolio risk for AAPL"})

    assert result["allowed"] is True
    assert result["blocked"] is False
    assert result["reason"] == "Finance-related query approved."


def test_guardrail_uses_llm_for_ambiguous_query(monkeypatch):
    captured: dict = {}

    def fake_chat(message, system_prompt=None, max_retries=3):
        captured["message"] = message
        captured["system_prompt"] = system_prompt
        captured["max_retries"] = max_retries
        return '{"allowed": false, "reason": "Not finance related."}'

    monkeypatch.setattr(main, "chat", fake_chat)

    result = main.check_search_query({"query": "best pasta recipe"})

    assert result["allowed"] is False
    assert result["blocked"] is True
    assert result["reason"] == "Not finance related."
    assert captured["max_retries"] == 1
    assert "best pasta recipe" in captured["message"]


def test_search_knowledge_packs_context_and_calls_llm(monkeypatch):
    captured: dict = {}

    def fake_chat(prompt):
        captured["prompt"] = prompt
        return "Use AML review steps."

    monkeypatch.setattr(main, "chat", fake_chat)

    result = main.search_knowledge_base(
        {
            "query": "How should AML alerts be reviewed?",
            "context": [
                {"document": "AML review requires triage and escalation."},
                {"content": "Customer risk rating matters."},
            ],
        }
    )

    assert result["agent"] == "KnowledgeSearch"
    assert result["agent_response"] == "Use AML review steps."
    assert result["context_count"] == 2
    assert "[Document 1]" in captured["prompt"]
    assert "AML review requires triage" in captured["prompt"]
    assert "How should AML alerts be reviewed?" in captured["prompt"]


def test_search_knowledge_marks_rate_limit(monkeypatch):
    monkeypatch.setattr(
        main,
        "chat",
        lambda *_: (_ for _ in ()).throw(RuntimeError("429 rate limit")),
    )

    result = main.search_knowledge_base({"query": "portfolio risk"})

    assert result["rate_limited"] is True
    assert "rate-limited" in result["agent_response"]
