"""Compliance logic aligned to the legacy prompts."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.llm import chat


ALLOWED_TRANSACTION_TYPES = {"buy", "sell", "dividend"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compliance_contract(audience: str = "analyst") -> str:
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


def _transaction_amount(txn: dict) -> float:
    explicit = txn.get("amount") or txn.get("total_amount")
    if explicit is not None:
        try:
            return float(explicit)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(txn.get("quantity") or 0) * float(txn.get("price") or 0)
    except (TypeError, ValueError):
        return 0.0


def _compliance_prechecks(transactions: list[dict]) -> dict:
    types = [(txn.get("type") or txn.get("transaction_type") or "").lower() for txn in transactions]
    unsupported_types = sorted(
        {txn_type for txn_type in types if txn_type and txn_type not in ALLOWED_TRANSACTION_TYPES}
    )
    symbol_counts: dict[str, int] = {}
    large_transactions = 0
    for txn in transactions:
        symbol = str(txn.get("symbol") or "").upper()
        if symbol:
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        if _transaction_amount(txn) >= 10000:
            large_transactions += 1

    repeated_symbols = sorted(
        symbol for symbol, count in symbol_counts.items() if count >= 4
    )
    findings: list[str] = []
    if unsupported_types:
        findings.append(
            "Unsupported transaction types found: " + ", ".join(unsupported_types) + "."
        )
    if len(transactions) >= 20:
        findings.append(
            "High transaction volume should be reviewed for reporting and surveillance thresholds."
        )
    if repeated_symbols:
        findings.append(
            "Repeated same-symbol activity may need trading-policy review: "
            + ", ".join(repeated_symbols[:5])
            + "."
        )
    if large_transactions:
        findings.append(
            f"{large_transactions} transaction(s) meet the large-notional review threshold."
        )

    return {
        "transaction_count": len(transactions),
        "unsupported_types": unsupported_types,
        "large_transactions": large_transactions,
        "repeated_symbols": repeated_symbols,
        "findings": findings,
    }


def _severity_from_prechecks(prechecks: dict, text: str = "") -> str:
    if prechecks["large_transactions"] >= 3 or prechecks["unsupported_types"]:
        return "high"
    if prechecks["transaction_count"] >= 20 or prechecks["repeated_symbols"]:
        return "medium"
    return risk_severity(text=text) if text else "low"


def _actions_for_severity(severity: str) -> list[str]:
    if severity in {"critical", "high"}:
        return [
            "Queue the activity for compliance analyst review.",
            "Validate transaction purpose and available customer context.",
            "Document whether reporting or escalation thresholds are met.",
        ]
    if severity == "medium":
        return [
            "Document the policy checks performed.",
            "Monitor for repeated activity or related alerts.",
        ]
    return ["Continue routine compliance monitoring."]


def review_transactions_compliance(transactions: list[dict]) -> dict:
    prechecks = _compliance_prechecks(transactions)
    prompt = (
        "You are a compliance officer. Review these transactions for regulatory compliance.\n\n"
        f"Transactions:\n{json.dumps(transactions[:20], indent=2)}\n\n"
        f"Deterministic Prechecks:\n{json.dumps(prechecks, indent=2)}\n\n"
        f"{_compliance_contract('analyst')}\n"
        "Check trading-policy, reporting, tax, and AML/KYC concerns without overstating certainty."
    )
    response = chat(prompt)
    findings = response or "Compliance review unavailable."
    severity = _severity_from_prechecks(prechecks, findings)
    return {
        "agent": "ComplianceOfficer",
        "timestamp": _timestamp(),
        "review_type": "transaction_compliance",
        "findings": findings,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(findings, "Compliance review unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=prechecks["findings"]
            or [f"Transactions reviewed: {prechecks['transaction_count']}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Re-run compliance review if new transactions or alerts appear."],
            raw_text=findings,
        ),
    }


def generate_tax_report(transaction_history: list[dict], year: int) -> dict:
    prechecks = _compliance_prechecks(transaction_history)
    prompt = (
        f"You are a tax specialist. Generate a tax report for {year} based on:\n\n"
        f"Transactions:\n{json.dumps(transaction_history, indent=2)}\n\n"
        f"Deterministic Prechecks:\n{json.dumps(prechecks, indent=2)}\n\n"
        f"{_compliance_contract('analyst')}\n"
        "Summarize capital-gains considerations, dividends, tax-loss opportunities, and next steps."
    )
    response = chat(prompt)
    report = response or "Tax report unavailable."
    severity = _severity_from_prechecks(prechecks, report)
    return {
        "agent": "ComplianceOfficer",
        "timestamp": _timestamp(),
        "report_type": "tax",
        "year": year,
        "report": report,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=_summary_from_text(report, "Tax report unavailable."),
            severity=severity,
            confidence="medium",
            key_factors=prechecks["findings"]
            or [f"Transactions reviewed for tax year {year}: {prechecks['transaction_count']}"],
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Confirm tax treatment with authoritative records before filing."],
            raw_text=report,
        ),
    }


def invoke(portfolio: dict, transactions: list[dict], mode: str = "quick") -> dict:
    if mode == "full":
        result = review_transactions_compliance(transactions)
        return {
            "agent": "compliance",
            "mode": mode,
            "summary": result["findings"],
            "findings": [result["findings"]],
            "prechecks": result["prechecks"],
            "structured_output": result["structured_output"],
        }

    prechecks = _compliance_prechecks(transactions)
    findings = list(prechecks["findings"])
    if not findings:
        findings.append("Quick compliance screen found no immediate policy concern.")
    severity = _severity_from_prechecks(prechecks)
    summary = " ".join(findings)

    return {
        "agent": "compliance",
        "mode": mode,
        "summary": summary,
        "findings": findings,
        "prechecks": prechecks,
        "structured_output": build_structured_output(
            summary=summary,
            severity=severity,
            confidence="high",
            key_factors=findings,
            recommended_actions=_actions_for_severity(severity),
            follow_up=["Run full compliance review if new risk signals emerge."],
            raw_text=summary,
        ),
    }


class ComplianceAgent:
    AGENT_DOMAIN = "compliance"

    def review_transactions_compliance(self, transactions: list[dict]) -> dict:
        return review_transactions_compliance(transactions)

    def generate_tax_report(self, transaction_history: list[dict], year: int) -> dict:
        return generate_tax_report(transaction_history, year)
