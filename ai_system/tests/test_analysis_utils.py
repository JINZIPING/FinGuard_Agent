from __future__ import annotations

from ai_system.app import analysis_utils


class FakeRiskEngine:
    def score(self, transaction: dict) -> dict:
        if transaction.get("fail"):
            raise RuntimeError("scoring failed")
        return {
            "final_score": transaction["score"],
            "risk_label": transaction["label"],
            "method": "fake",
            "hard_block": transaction.get("hard_block", False),
            "flags": transaction.get("flags", []),
        }


def test_format_helpers_are_stable():
    assert analysis_utils.format_dict({"a": 1, "b": "two"}) == "  a: 1\n  b: two"
    assert analysis_utils.format_list(["first", "second"]) == "  1. first\n  2. second"


def test_ml_score_transactions_returns_empty_without_engine(monkeypatch):
    monkeypatch.setattr(analysis_utils, "get_risk_engine", lambda: None)

    assert analysis_utils.ml_score_transactions([{"score": 10}]) == ""
    assert analysis_utils.ml_score_transactions([]) == ""


def test_ml_score_transactions_summarizes_first_twenty_and_failures(monkeypatch):
    transactions = [
        {"score": 95, "label": "critical", "hard_block": True, "flags": ["AML"]},
        {"score": 80, "label": "high", "flags": ["VELOCITY"]},
        {"score": 30, "label": "low"},
        {"fail": True},
    ]
    transactions.extend({"score": 10, "label": "low"} for _ in range(25))
    monkeypatch.setattr(analysis_utils, "get_risk_engine", lambda: FakeRiskEngine())

    summary = analysis_utils.ml_score_transactions(transactions)

    assert "Total scanned: 20 | High/Critical: 2" in summary
    assert "Txn 1: score=95/100 label=critical method=fake hard_block=True flags=[AML]" in summary
    assert "Txn 2: score=80/100 label=high method=fake hard_block=False flags=[VELOCITY]" in summary
    assert "Txn 4: ML scoring failed" in summary
    assert "Txn 21" not in summary
