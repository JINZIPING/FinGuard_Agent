"""Compliance logic aligned to the legacy prompts."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ai_system.app.agent_output import build_structured_output, risk_severity
from ai_system.app.llm import chat


ALLOWED_TRANSACTION_TYPES = {"buy", "sell", "dividend"}
LARGE_NOTIONAL_REVIEW_THRESHOLD = 10000
HIGH_ACTIVITY_TRANSACTION_COUNT = 20
REPEATED_SYMBOL_ACTIVITY_COUNT = 4


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


def _rule_hit(
    *,
    rule_id: str,
    severity: str,
    basis: str,
    description: str,
    evidence: dict,
) -> dict:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "basis": basis,
        "description": description,
        "evidence": evidence,
    }


def _compliance_prechecks(transactions: list[dict]) -> dict:
    types = [
        (txn.get("type") or txn.get("transaction_type") or "").lower()
        for txn in transactions
    ]
    unsupported_types = sorted(
        {
            txn_type
            for txn_type in types
            if txn_type and txn_type not in ALLOWED_TRANSACTION_TYPES
        }
    )
    symbol_counts: dict[str, int] = {}
    large_transactions = 0
    for txn in transactions:
        symbol = str(txn.get("symbol") or "").upper()
        if symbol:
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        if _transaction_amount(txn) >= LARGE_NOTIONAL_REVIEW_THRESHOLD:
            large_transactions += 1

    repeated_symbols = sorted(
        symbol
        for symbol, count in symbol_counts.items()
        if count >= REPEATED_SYMBOL_ACTIVITY_COUNT
    )
    rule_hits: list[dict] = []
    if unsupported_types:
        rule_hits.append(
            _rule_hit(
                rule_id="UNSUPPORTED_TXN_TYPE",
                severity="high",
                basis="internal_schema_control",
                description=(
                    "Unsupported transaction types found: "
                    + ", ".join(unsupported_types)
                    + "."
                ),
                evidence={"unsupported_types": unsupported_types},
            )
        )
    if len(transactions) >= HIGH_ACTIVITY_TRANSACTION_COUNT:
        rule_hits.append(
            _rule_hit(
                rule_id="HIGH_ACTIVITY_VOLUME",
                severity="medium",
                basis="internal_surveillance_heuristic",
                description=(
                    "High transaction volume should be reviewed for reporting and "
                    "surveillance thresholds."
                ),
                evidence={
                    "transaction_count": len(transactions),
                    "threshold": HIGH_ACTIVITY_TRANSACTION_COUNT,
                },
            )
        )
    if repeated_symbols:
        rule_hits.append(
            _rule_hit(
                rule_id="REPEATED_SYMBOL_ACTIVITY",
                severity="medium",
                basis="trading_policy_surveillance_heuristic",
                description=(
                    "Repeated same-symbol activity may need trading-policy review: "
                    + ", ".join(repeated_symbols[:5])
                    + "."
                ),
                evidence={
                    "repeated_symbols": repeated_symbols,
                    "threshold": REPEATED_SYMBOL_ACTIVITY_COUNT,
                },
            )
        )
    if large_transactions:
        rule_hits.append(
            _rule_hit(
                rule_id="LARGE_NOTIONAL_REVIEW",
                severity="medium",
                basis="internal_surveillance_heuristic",
                description=(
                    f"{large_transactions} transaction(s) meet the "
                    "large-notional review threshold."
                ),
                evidence={
                    "transaction_count": large_transactions,
                    "threshold": LARGE_NOTIONAL_REVIEW_THRESHOLD,
                    "threshold_note": (
                        "Internal notional review threshold; not a CTR determination."
                    ),
                },
            )
        )
    findings = [hit["description"] for hit in rule_hits]

    return {
        "transaction_count": len(transactions),
        "unsupported_types": unsupported_types,
        "large_transactions": large_transactions,
        "repeated_symbols": repeated_symbols,
        "rule_hits": rule_hits,
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


def review_transactions_compliance(
    transactions: list[dict], customer_context: dict | None = None
) -> dict:
    prechecks = _compliance_prechecks(transactions)
    prompt = (
        "You are a compliance officer. Review these transactions for regulatory compliance.\n\n"
        f"Transactions:\n{json.dumps(transactions[:20], indent=2)}\n\n"
        f"Customer Context:\n{json.dumps(customer_context or {}, indent=2)}\n\n"
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


def invoke(
    portfolio: dict,
    transactions: list[dict],
    mode: str = "quick",
    customer_context: dict | None = None,
) -> dict:
    if mode == "full":
        result = review_transactions_compliance(transactions, customer_context)
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

    def review_transactions_compliance(
        self, transactions: list[dict], customer_context: dict | None = None
    ) -> dict:
        return review_transactions_compliance(transactions, customer_context)

