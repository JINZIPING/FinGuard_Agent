"""LangGraph nodes for portfolio review with legacy-compatible semantics."""

from __future__ import annotations

import re
from time import perf_counter

from ai_system.app.agents import (
    alert_intake_agent as alert_intake,
    compliance_agent as compliance,
    customer_context_agent as customer_context,
    escalation_case_summary_agent as escalation,
    explanation_agent as explanation,
    market_intelligence_agent as market,
    portfolio_analysis_agent as portfolio,
    risk_assessment_agent as risk,
)
from ai_system.app.analysis_utils import ml_score_transactions
from ai_system.app.llm import get_last_thinking, is_rate_limit_error
from ai_system.langgraph.contracts import (
    CONTRACT_VERSION,
    normalize_agent_artifact,
    serialize_agent_artifact,
)
from ai_system.langgraph.state import PortfolioAnalysisState

try:
    from langsmith import traceable
except ImportError:  # pragma: no cover - tracing is optional at import time

    def traceable(*_: object, **__: object) -> object:
        def decorator(func: object) -> object:
            return func

        return decorator


def _truncate_error(exc: Exception) -> str:
    return str(exc)[:200]


def _clean_one_line(text: str, max_len: int = 180) -> str:
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text or "")
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"^[\-\*\u2022]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = " ".join(cleaned.split()).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def _first_text(value: object, fallback: str) -> str:
    if isinstance(value, (list, tuple)):
        for item in value:
            text = str(item).strip()
            if text:
                return text
        return fallback
    text = str(value or "").strip()
    return text or fallback


def _emit_llm_thinking(state: PortfolioAnalysisState, node: str, agent_name: str) -> None:
    thinking = get_last_thinking()
    if thinking:
        _append_trace(
            state,
            {
                "type": "thinking",
                "node": node,
                "agent": agent_name,
                "name": agent_name,
                "step": 1,
                "analysis_type": "LLM Reasoning",
                "details": thinking,
                "status": "in_progress",
            },
        )


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _structured_signal_summary(
    label: str,
    payload: dict,
    *,
    signal_parts: list[str] | None = None,
    summary_fallback: str,
    driver_fallback: str,
    action_fallback: str,
) -> str:
    structured = payload.get("structured_output", {}) or {}
    summary = _clean_one_line(
        str(
            structured.get("summary")
            or payload.get("summary")
            or payload.get("analysis")
            or summary_fallback
        )
    )
    severity = str(structured.get("severity") or "unknown").strip()
    confidence = str(structured.get("confidence") or "unknown").strip()
    driver = _clean_one_line(
        _first_text(structured.get("key_factors"), driver_fallback),
        max_len=110,
    )
    action = _clean_one_line(
        _first_text(structured.get("recommended_actions"), action_fallback),
        max_len=110,
    )
    parts = [f"severity={severity}", f"confidence={confidence}"] + (signal_parts or [])
    return (
        f"{label} {summary}\n"
        f"Signal: {'; '.join(parts)}; driver={driver}\n"
        f"Action: {action}"
    )


def _append_trace(state: PortfolioAnalysisState, event: dict) -> None:
    trace = state.setdefault("analysis_trace", [])
    trace.append(
        {
            "sequence": len(trace) + 1,
            "contract_version": CONTRACT_VERSION,
            "agent": None,
            "crew": None,
            "structured_summary": None,
            "severity": None,
            "confidence": None,
            "evidence_refs": [],
            "fallback_used": False,
            "fallback_reason": None,
            "rate_limited": False,
            "data_basis": None,
            **event,
        }
    )


def _artifact_trace_fields(
    payload: dict | None,
    *,
    evidence_refs: list[str] | None = None,
    fallback_reason: str | None = None,
) -> dict:
    artifact = payload or {}
    structured = artifact.get("structured_output", {}) or {}
    return {
        "structured_summary": structured.get("summary"),
        "severity": structured.get("severity"),
        "confidence": structured.get("confidence"),
        "evidence_refs": evidence_refs or [],
        "fallback_used": bool(
            artifact.get("rate_limited")
            or artifact.get("success") is False
            or fallback_reason
        ),
        "fallback_reason": fallback_reason,
        "rate_limited": bool(artifact.get("rate_limited")),
        "data_basis": artifact.get("data_basis"),
    }


def _terminal_event(
    state: PortfolioAnalysisState,
    *,
    node: str,
    title: str,
    body: str,
) -> None:
    _append_trace(
        state,
        {
            "type": "terminal",
            "node": node,
            "title": title,
            "body": body,
            "status": "completed",
        },
    )


def _divider_event(
    state: PortfolioAnalysisState,
    *,
    node: str,
    label: str,
    completed: bool = True,
) -> None:
    _append_trace(
        state,
        {
            "type": "divider",
            "node": node,
            "label": label,
            "completed": completed,
            "status": "completed" if completed else "started",
        },
    )


def _agent_event(
    state: PortfolioAnalysisState,
    *,
    node: str,
    crew: str,
    name: str,
    body: str,
    duration_ms: int,
    status: str = "completed",
    payload: dict | None = None,
    evidence_refs: list[str] | None = None,
    fallback_reason: str | None = None,
) -> None:
    _append_trace(
        state,
        {
            "type": "agent",
            "node": node,
            "crew": crew,
            "agent": name,
            "name": name,
            "status": status,
            "duration_ms": duration_ms,
            "body": body,
            **_artifact_trace_fields(
                payload,
                evidence_refs=evidence_refs,
                fallback_reason=fallback_reason,
            ),
        },
    )


def _thinking_step_event(
    state: PortfolioAnalysisState,
    *,
    node: str,
    agent_name: str,
    step_num: int,
    analysis_type: str,
    details: str,
) -> None:
    """Emit a thinking step event for intermediate reasoning."""
    _append_trace(
        state,
        {
            "type": "thinking",
            "node": node,
            "agent": agent_name,
            "name": agent_name,
            "step": step_num,
            "analysis_type": analysis_type,
            "details": details,
            "status": "in_progress",
        },
    )


def _emit_thinking_steps(
    state: PortfolioAnalysisState,
    node: str,
    agent_name: str,
    thinking_steps: list[dict] | None,
) -> None:
    """Emit all thinking steps from an agent response."""
    if thinking_steps:
        for step_info in thinking_steps:
            if step_info:  # skip None entries
                _thinking_step_event(
                    state,
                    node=node,
                    agent_name=agent_name,
                    step_num=step_info.get("step", 0),
                    analysis_type=step_info.get("analysis", ""),
                    details=step_info.get("details", ""),
                )


def _market_snapshot(symbols: list[str]) -> str:
    if not symbols:
        return "No active symbols were available for a focused market sentiment pass."
    return (
        f"Market context was summarized for {', '.join(symbols[:5])}. "
        "Use the dedicated sentiment endpoint for a deeper symbol-level read."
    )


def _portfolio_value_band(total_value: float) -> str:
    if total_value >= 250000:
        return "premium"
    if total_value >= 100000:
        return "affluent"
    return "standard"


def _derive_customer_inputs(
    portfolio_data: dict, transactions: list[dict]
) -> tuple[str, dict]:
    assets = portfolio_data.get("assets", []) or []
    total_value = float(portfolio_data.get("total_value") or 0)
    cash_balance = float(portfolio_data.get("cash_balance") or 0)
    cash_ratio = (cash_balance / total_value) if total_value else 0.0
    symbol_counts: dict[str, int] = {}
    large_transactions = 0
    for txn in transactions:
        symbol = str(txn.get("symbol") or "").upper()
        if symbol:
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        try:
            amount = float(txn.get("amount") or 0) or float(txn.get("quantity") or 0) * float(txn.get("price") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount >= 10000:
            large_transactions += 1

    behavioral_flags: list[str] = []
    if any(count >= 4 for count in symbol_counts.values()):
        behavioral_flags.append("repeat_symbol_activity")
    if large_transactions:
        behavioral_flags.append("large_recent_transactions")
    if cash_ratio < 0.05 and total_value > 0:
        behavioral_flags.append("thin_cash_buffer")

    customer_id = str(
        portfolio_data.get("customer_id")
        or portfolio_data.get("owner_id")
        or portfolio_data.get("user_id")
        or portfolio_data.get("id")
        or "portfolio-customer"
    )
    profile_data = {
        "portfolio_value": total_value,
        "cash_balance": cash_balance,
        "segment": portfolio_data.get("segment") or _portfolio_value_band(total_value),
        "risk_profile": portfolio_data.get("risk_profile")
        or ("high risk" if large_transactions >= 2 else "moderate"),
        "risk_tolerance": portfolio_data.get("risk_tolerance")
        or ("aggressive" if behavioral_flags else "moderate"),
        "investment_goals": portfolio_data.get("investment_goals")
        or "capital preservation with diversified growth",
        "asset_count": len(assets),
        "transaction_count": len(transactions),
        "behavioral_flags": behavioral_flags,
    }
    return customer_id, profile_data


def _summarize_customer_context(payload: dict) -> str:
    score = payload.get("consistency_score")
    label = payload.get("consistency_label") or "unknown"
    signal_parts = []
    if score is not None:
        signal_parts.append(f"consistency={score}/100 ({label})")
    return _structured_signal_summary(
        "Customer",
        payload,
        signal_parts=signal_parts,
        summary_fallback="Customer context review returned no analyst summary.",
        driver_fallback="No customer-context driver extracted.",
        action_fallback="Use the profile for routine context enrichment.",
    )


def _summarize_alert_intake(payload: dict) -> str:
    return _structured_signal_summary(
        "Alert intake",
        payload,
        signal_parts=[
            f"urgency={payload.get('urgency_level', 'Unknown')}",
            f"priority={payload.get('priority_tier', 'P4')}",
            f"escalate={payload.get('escalation_recommendation', 'No')}",
        ],
        summary_fallback="Alert intake review returned no routing summary.",
        driver_fallback="No alert routing driver extracted.",
        action_fallback="Continue standard alert triage.",
    )


def _summarize_escalation(
    evaluation_payload: dict,
    case_summary_payload: dict,
) -> str:
    summary_payload = case_summary_payload or evaluation_payload
    evidence = _first_text(
        evaluation_payload.get("evidence_portfolio"),
        "No evidence portfolio was captured.",
    )
    return _structured_signal_summary(
        "Escalation",
        summary_payload,
        signal_parts=[
            f"action={evaluation_payload.get('action_recommendation', 'Decline')}",
            f"priority={evaluation_payload.get('priority_tier', 'P4')}",
            f"evidence={_clean_one_line(evidence, max_len=90)}",
        ],
        summary_fallback="Escalation review returned no final case summary.",
        driver_fallback="No escalation driver extracted.",
        action_fallback="Continue standard case monitoring and document closure rationale.",
    )


def _build_explanation_input(
    state: PortfolioAnalysisState,
    alert_payload: dict,
    crew1_results: dict,
    crew2_results: dict,
) -> dict:
    return {
        "portfolio": {
            "id": (state.get("portfolio") or {}).get("id"),
            "name": (state.get("portfolio") or {}).get("name"),
            "total_value": (state.get("portfolio") or {}).get("total_value"),
        },
        "ml_summary": state.get("ml_summary", ""),
        "risk_assessment": (crew1_results.get("risk_assessment", {}) or {}).get(
            "structured_output", {}
        ),
        "risk_detection": (crew1_results.get("risk_detection", {}) or {}).get(
            "structured_output", {}
        ),
        "compliance": (crew1_results.get("compliance", {}) or {}).get(
            "structured_output", {}
        ),
        "portfolio_analysis": (crew2_results.get("portfolio_analysis", {}) or {}).get(
            "structured_output", {}
        ),
        "market_intelligence": (
            crew2_results.get("market_intelligence", {}) or {}
        ).get("structured_output", {}),
        "customer_context": (crew2_results.get("customer_context", {}) or {}).get(
            "structured_output", {}
        ),
        "alert_intake": (alert_payload.get("structured_output", {}) or {}),
    }


def _build_escalation_inputs(
    state: PortfolioAnalysisState,
    alert_payload: dict,
    explanation_payload: dict,
    crew1_results: dict,
    crew2_results: dict,
    *,
    max_risk_score: float | int | None,
    hard_block: bool,
    compliance_rule_hits: list[dict],
) -> tuple[dict, dict, list[dict], list[dict]]:
    portfolio = state.get("portfolio") or {}
    case_data = {
        "id": state.get("request_id") or portfolio.get("id"),
        "portfolio_id": portfolio.get("id"),
        "portfolio_name": portfolio.get("name"),
        "risk_score": max_risk_score,
        "hard_block": hard_block,
        "compliance_rule_hits": compliance_rule_hits,
        "customer_consistency": (
            crew2_results.get("customer_context", {}) or {}
        ).get("consistency_label"),
        "alert_intake": alert_payload.get("structured_output", {}),
        "explanation": explanation_payload.get("structured_output", {}),
    }
    severity_factors = {
        "ml_summary": state.get("ml_summary", ""),
        "risk_assessment": (
            crew1_results.get("risk_assessment", {}) or {}
        ).get("structured_output", {}),
        "risk_detection": (
            crew1_results.get("risk_detection", {}) or {}
        ).get("structured_output", {}),
        "compliance": (crew1_results.get("compliance", {}) or {}).get(
            "structured_output", {}
        ),
        "portfolio_analysis": (
            crew2_results.get("portfolio_analysis", {}) or {}
        ).get("structured_output", {}),
        "market_intelligence": (
            crew2_results.get("market_intelligence", {}) or {}
        ).get("structured_output", {}),
        "customer_context": (
            crew2_results.get("customer_context", {}) or {}
        ).get("structured_output", {}),
        "regulatory": " ".join(
            hit.get("description", "") for hit in compliance_rule_hits
        ),
        "hard_block": hard_block,
    }
    interactions = [
        {
            "agent": "risk_assessment",
            "structured_output": (
                crew1_results.get("risk_assessment", {}) or {}
            ).get("structured_output", {}),
        },
        {
            "agent": "risk_detection",
            "structured_output": (
                crew1_results.get("risk_detection", {}) or {}
            ).get("structured_output", {}),
        },
        {
            "agent": "compliance",
            "structured_output": (
                crew1_results.get("compliance", {}) or {}
            ).get("structured_output", {}),
            "rule_hits": compliance_rule_hits,
        },
        {
            "agent": "portfolio_analysis",
            "structured_output": (
                crew2_results.get("portfolio_analysis", {}) or {}
            ).get("structured_output", {}),
        },
        {
            "agent": "market_intelligence",
            "structured_output": (
                crew2_results.get("market_intelligence", {}) or {}
            ).get("structured_output", {}),
        },
        {
            "agent": "customer_context",
            "structured_output": (
                crew2_results.get("customer_context", {}) or {}
            ).get("structured_output", {}),
            "consistency_label": (
                crew2_results.get("customer_context", {}) or {}
            ).get("consistency_label"),
        },
    ]
    decisions = [
        {
            "agent": "alert_intake",
            "structured_output": alert_payload.get("structured_output", {}),
            "priority_tier": alert_payload.get("priority_tier"),
            "urgency_level": alert_payload.get("urgency_level"),
            "escalation_recommendation": alert_payload.get(
                "escalation_recommendation"
            ),
        },
        {
            "agent": "explanation",
            "structured_output": explanation_payload.get("structured_output", {}),
            "summary": explanation_payload.get("summary"),
        },
    ]
    return case_data, severity_factors, interactions, decisions


@traceable(name="langgraph_ingest_request", run_type="chain")
def ingest_request(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    state.setdefault("findings", [])
    state.setdefault("errors", [])
    state.setdefault("analysis_trace", [])
    state.setdefault("crews_run", 0)
    state.setdefault("rate_limited", False)
    state.setdefault("crew1_results", {})
    state.setdefault("crew2_results", {})
    state.setdefault("crew3_results", {})
    state["route"] = state.get("route") or (
        "quick" if len(state.get("transactions", [])) < 10 else "full"
    )

    portfolio_data = state.get("portfolio") or {}
    transactions = state.get("transactions") or []
    customer_id, customer_profile = _derive_customer_inputs(portfolio_data, transactions)
    state["customer_context_seed"] = {
        "customer_id": customer_id,
        "profile_data": customer_profile,
    }
    state["portfolio_summary"] = (
        f"Portfolio '{portfolio_data.get('name')}': "
        f"${portfolio_data.get('total_value', 0):,.0f} total, "
        f"{len(portfolio_data.get('assets', []))} assets, "
        f"symbols: {', '.join(asset.get('symbol', '') for asset in portfolio_data.get('assets', [])[:5] if asset.get('symbol'))}"
    )
    state["transaction_summary"] = (
        f"Recent {len(transactions[:10])} transactions; "
        f"types: {', '.join(sorted({txn.get('type', 'unknown') for txn in transactions[:10]}))}"
    )
    state["ml_summary"] = ml_score_transactions(transactions[:10])
    _terminal_event(
        state,
        node="ingest_request",
        title="LangGraph Request Ingested",
        body=(
            f"route={state['route']}\n"
            f"{state['portfolio_summary']}\n"
            f"{state['transaction_summary']}\n\n"
            f"ML pre-screening:\n{state['ml_summary']}"
        ),
    )
    return state


@traceable(name="langgraph_quick_recommendation", run_type="chain")
def run_quick_recommendation(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    start = perf_counter()
    state["response"] = risk.quick_portfolio_recommendation(
        state.get("portfolio") or {},
        state.get("transactions") or [],
    )
    _divider_event(
        state,
        node="run_quick_recommendation",
        label="Quick recommendation completed - agents: Risk Assessment",
    )
    _agent_event(
        state,
        node="run_quick_recommendation",
        crew="Quick Recommendation",
        name="Risk Assessment Agent",
        body=state["response"].get("recommendation", str(state["response"])),
        duration_ms=_elapsed_ms(start),
        payload=state["response"],
        evidence_refs=["response.structured_output"],
    )
    return state


@traceable(name="langgraph_run_full_crews", run_type="chain")
def run_full_crews(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    """
    Legacy-named full-run entrypoint.

    The project report defines the three crews as sequential: later crews consume
    the structured outputs created by earlier crews. We therefore execute them in
    order even though the historical helper name still mentions "parallel".
    """
    for crew_name, runner in (
        ("crew1", run_full_crew_one),
        ("crew2", run_full_crew_two),
        ("crew3", run_full_crew_three),
    ):
        try:
            state = runner(state)
            if state.get("rate_limited"):
                break
        except Exception as exc:
            state.setdefault("errors", []).append(
                f"{crew_name} failed: {_truncate_error(exc)}"
            )
            break

    return state


@traceable(name="langgraph_crew_1_risk_analysis", run_type="chain")
def run_full_crew_one(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    if state.get("rate_limited"):
        return state

    portfolio_data = state.get("portfolio") or {}
    transactions = state.get("transactions") or []
    customer_context_seed = state.get("customer_context_seed") or {}
    customer_profile = customer_context_seed.get("profile_data", {})
    start = perf_counter()

    try:
        ml_scores = [risk.score_transaction(txn) for txn in transactions[:10]]
        risk_assessment = normalize_agent_artifact(
            risk.assess_portfolio_risk(
            portfolio_data,
            {"volatility": "current market conditions"},
            customer_context=customer_profile,
            ),
            default_agent="RiskAssessment",
            primary_text_keys=("risk_analysis", "summary", "analysis"),
        )
        _emit_llm_thinking(state, "run_full_crew_one", "Risk Assessment Agent")
        fraud_assessment = normalize_agent_artifact(
            risk.detect_fraud_risk(transactions, portfolio_data, ml_scores),
            default_agent="RiskDetector",
            primary_text_keys=("assessment", "summary", "analysis"),
        )
        _emit_llm_thinking(state, "run_full_crew_one", "Risk Detection Agent")
        compliance_payload = normalize_agent_artifact(
            compliance.invoke(
                portfolio_data,
                transactions,
                mode="full",
                customer_context=customer_profile,
            ),
            default_agent="Compliance",
            primary_text_keys=("summary", "analysis"),
        )
        compliance_structured = compliance_payload.get("structured_output", {}) or {}
        compliance_prechecks = compliance_payload.get("prechecks", {}) or {}
        compliance_rule_hits = compliance_prechecks.get("rule_hits", []) or []
        compliance_rule = compliance_rule_hits[0] if compliance_rule_hits else {}
        compliance_summary_source = (
            f"{len(compliance_rule_hits)} compliance precheck(s) require analyst review."
            if compliance_rule_hits
            else compliance_structured.get("summary")
            or compliance_payload.get("summary")
            or ""
        )
        compliance_summary = _clean_one_line(str(compliance_summary_source).strip())
        compliance_severity = str(
            compliance_rule.get("severity")
            or compliance_structured.get("severity")
            or "unknown"
        ).strip()
        compliance_confidence = str(
            compliance_structured.get("confidence") or "unknown"
        ).strip()
        compliance_basis = _clean_one_line(
            str(compliance_rule.get("basis") or "agent_structured_output"),
            max_len=80,
        )
        compliance_driver = _clean_one_line(
            str(
                compliance_rule.get("description")
                or _first_text(
                    compliance_structured.get("key_factors"),
                    "No compliance driver extracted.",
                )
            ),
            max_len=110,
        )
        compliance_action = _clean_one_line(
            _first_text(
                compliance_structured.get("recommended_actions"),
                "Continue analyst review using available case context.",
            ),
            max_len=110,
        )
        if compliance_summary:
            compliance_result = (
                f"Compliance {compliance_summary}\n"
                f"Signal: severity={compliance_severity}; confidence={compliance_confidence}; basis={compliance_basis}; driver={compliance_driver}\n"
                f"Action: {compliance_action}"
            )
        else:
            compliance_result = "Compliance review returned no analyst summary."
        state["crew1_results"] = {
            "ml_scores": ml_scores,
            "risk_assessment": risk_assessment,
            "risk_detection": fraud_assessment,
            "compliance": compliance_payload,
        }
        state["crew1_output"] = (
            f"{risk_assessment['risk_analysis']}\n\n"
            f"{fraud_assessment['assessment']}\n\n"
            f"{compliance_result}"
        )
        state["crews_run"] = 1
        duration_ms = _elapsed_ms(start)
        
        # Emit thinking steps for Risk Assessment
        _emit_thinking_steps(
            state,
            node="run_full_crew_one",
            agent_name="Risk Assessment Agent",
            thinking_steps=risk_assessment.get("thinking_steps"),
        )
        
        # Emit thinking steps for Fraud Detection
        _emit_thinking_steps(
            state,
            node="run_full_crew_one",
            agent_name="Risk Detection Agent",
            thinking_steps=fraud_assessment.get("thinking_steps"),
        )
        
        _terminal_event(
            state,
            node="run_full_crew_one",
            title="Transaction Risk Analysis",
            body=state.get("ml_summary", "No ML pre-screening summary available."),
        )
        _divider_event(
            state,
            node="run_full_crew_one",
            label="Crew 1: Risk Analysis completed - agents: Risk Assessment, Risk Detection, Compliance",
        )
        _agent_event(
            state,
            node="run_full_crew_one",
            crew="Crew 1: Risk Analysis",
            name="Risk Assessment Agent",
            body=risk_assessment["risk_analysis"],
            duration_ms=duration_ms,
            payload=risk_assessment,
            evidence_refs=["crew1_results.risk_assessment"],
        )
        _agent_event(
            state,
            node="run_full_crew_one",
            crew="Crew 1: Risk Analysis",
            name="Risk Detection Agent",
            body=fraud_assessment["assessment"],
            duration_ms=duration_ms,
            payload=fraud_assessment,
            evidence_refs=["crew1_results.risk_detection"],
        )
        _agent_event(
            state,
            node="run_full_crew_one",
            crew="Crew 1: Risk Analysis",
            name="Compliance Agent",
            body=compliance_result,
            duration_ms=duration_ms,
            payload=compliance_payload,
            evidence_refs=["crew1_results.compliance"],
        )
        return state
    except Exception as exc:
        if is_rate_limit_error(exc):
            state["rate_limited"] = True
            state["crews_run"] = 1
            state["crew1_output"] = (
                "Rate limit exceeded. Please wait 30 seconds and try again."
            )
            state["crew1_results"] = {}
            _agent_event(
                state,
                node="run_full_crew_one",
                crew="Crew 1: Risk Analysis",
                name="Risk Analysis Crew",
                body=state["crew1_output"],
                duration_ms=_elapsed_ms(start),
                status="rate_limited",
                fallback_reason="rate_limit",
            )
            return state

        state["crew1_output"] = f"Risk Analysis failed: {_truncate_error(exc)}"
        state["crews_run"] = 1
        state["crew1_results"] = {}
        _agent_event(
            state,
            node="run_full_crew_one",
            crew="Crew 1: Risk Analysis",
            name="Risk Analysis Crew",
            body=state["crew1_output"],
            duration_ms=_elapsed_ms(start),
            status="failed",
            fallback_reason="crew_failure",
        )
        return state


@traceable(name="langgraph_crew_2_portfolio_analysis", run_type="chain")
def run_full_crew_two(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    if state.get("rate_limited"):
        return state

    portfolio_data = state.get("portfolio") or {}
    transactions = state.get("transactions") or []
    customer_context_seed = state.get("customer_context_seed") or {}
    symbols = [
        asset.get("symbol")
        for asset in portfolio_data.get("assets", [])
        if asset.get("symbol")
    ]
    fallback_symbols = [txn.get("symbol") for txn in transactions if txn.get("symbol")][
        :5
    ]
    start = perf_counter()

    try:
        portfolio_analysis = normalize_agent_artifact(
            portfolio.analyze_portfolio(portfolio_data),
            default_agent="PortfolioAnalyzer",
            primary_text_keys=("analysis", "summary"),
        )
        _emit_llm_thinking(state, "run_full_crew_two", "Portfolio Analysis Agent")
        market_payload = normalize_agent_artifact(
            market.analyze_sentiment(
                symbols or fallback_symbols,
                detail_level="short",
            ),
            default_agent="MarketIntelligence",
            primary_text_keys=("sentiment_analysis", "summary", "analysis"),
        )
        _emit_llm_thinking(state, "run_full_crew_two", "Market Intelligence Agent")
        market_structured = market_payload.get("structured_output", {}) or {}
        market_summary = _clean_one_line(
            str(market_structured.get("summary") or "").strip()
        )
        market_severity = str(market_structured.get("severity") or "unknown").strip()
        market_confidence = str(market_structured.get("confidence") or "unknown").strip()
        market_driver = _clean_one_line(
            _first_text(
                market_structured.get("key_factors"),
                "No key driver extracted.",
            ),
            max_len=110,
        )
        market_action = _clean_one_line(
            _first_text(
                market_structured.get("recommended_actions"),
                "Validate with current market data before acting.",
            ),
            max_len=110,
        )
        if market_summary:
            market_result = (
                f"Market {market_summary}\n"
                f"Signal: severity={market_severity}; confidence={market_confidence}; driver={market_driver}\n"
                f"Action: {market_action}\n"
                "Scope: model-generated context; no live market feed.\n"
                "Use the dedicated sentiment endpoint for a deeper symbol-level read."
            )
        else:
            market_result = _market_snapshot(symbols or fallback_symbols)
        customer_id = str(
            customer_context_seed.get("customer_id")
            or portfolio_data.get("customer_id")
            or portfolio_data.get("id")
            or "portfolio-customer"
        )
        customer_profile = customer_context_seed.get("profile_data") or {}
        if not customer_profile:
            _, customer_profile = _derive_customer_inputs(portfolio_data, transactions)
        customer_payload = normalize_agent_artifact(
            customer_context.build_customer_profile(customer_id, customer_profile),
            default_agent="CustomerContext",
            primary_text_keys=("profile", "summary", "analysis"),
        )
        _emit_llm_thinking(state, "run_full_crew_two", "Customer Context Agent")
        customer_result = _summarize_customer_context(customer_payload)
        state["crew2_results"] = {
            "portfolio_analysis": portfolio_analysis,
            "market_intelligence": market_payload,
            "customer_context": customer_payload,
        }
        state["crew2_output"] = (
            f"{portfolio_analysis['analysis']}\n\n"
            f"{market_result}\n\n"
            f"{customer_result}"
        )
        state["crews_run"] = 2
        duration_ms = _elapsed_ms(start)
        
        # Emit thinking steps for Portfolio Analysis
        _emit_thinking_steps(
            state,
            node="run_full_crew_two",
            agent_name="Portfolio Analysis Agent",
            thinking_steps=portfolio_analysis.get("thinking_steps"),
        )
        
        _divider_event(
            state,
            node="run_full_crew_two",
            label="Crew 2: Portfolio Analysis completed - agents: Portfolio Analyst, Market Intelligence, Customer Context",
        )
        _agent_event(
            state,
            node="run_full_crew_two",
            crew="Crew 2: Portfolio Analysis",
            name="Portfolio Analysis Agent",
            body=portfolio_analysis["analysis"],
            duration_ms=duration_ms,
            payload=portfolio_analysis,
            evidence_refs=["crew2_results.portfolio_analysis"],
        )
        _agent_event(
            state,
            node="run_full_crew_two",
            crew="Crew 2: Portfolio Analysis",
            name="Market Intelligence Agent",
            body=market_result,
            duration_ms=duration_ms,
            payload=market_payload,
            evidence_refs=["crew2_results.market_intelligence"],
        )
        _agent_event(
            state,
            node="run_full_crew_two",
            crew="Crew 2: Portfolio Analysis",
            name="Customer Context Agent",
            body=customer_result,
            duration_ms=duration_ms,
            payload=customer_payload,
            evidence_refs=["crew2_results.customer_context"],
        )
        return state
    except Exception as exc:
        if is_rate_limit_error(exc):
            state["rate_limited"] = True
            state["crews_run"] = 2
            state["crew2_output"] = "Rate limit exceeded. Skipping remaining crews."
            state["crew2_results"] = {}
            _agent_event(
                state,
                node="run_full_crew_two",
                crew="Crew 2: Portfolio Analysis",
                name="Portfolio Analysis Crew",
                body=state["crew2_output"],
                duration_ms=_elapsed_ms(start),
                status="rate_limited",
                fallback_reason="rate_limit",
            )
            return state

        state["crew2_output"] = f"Portfolio Analysis failed: {_truncate_error(exc)}"
        state["crews_run"] = 2
        state["crew2_results"] = {}
        _agent_event(
            state,
            node="run_full_crew_two",
            crew="Crew 2: Portfolio Analysis",
            name="Portfolio Analysis Crew",
            body=state["crew2_output"],
            duration_ms=_elapsed_ms(start),
            status="failed",
            fallback_reason="crew_failure",
        )
        return state


@traceable(name="langgraph_crew_3_summary_escalation", run_type="chain")
def run_full_crew_three(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    if state.get("rate_limited"):
        return state

    portfolio_data = state.get("portfolio") or {}
    crew1_results = state.get("crew1_results") or {}
    crew2_results = state.get("crew2_results") or {}
    start = perf_counter()

    try:
        ml_scores = crew1_results.get("ml_scores", []) or []
        max_risk_score = max(
            (
                score.get("risk_score")
                for score in ml_scores
                if isinstance(score.get("risk_score"), (int, float))
            ),
            default=None,
        )
        hard_block = any(bool(score.get("hard_block")) for score in ml_scores)
        highest_risk_label = "low"
        for label in ("critical", "high", "medium", "low"):
            if any(score.get("risk_label") == label for score in ml_scores):
                highest_risk_label = label
                break

        compliance_payload = crew1_results.get("compliance", {}) or {}
        compliance_rule_hits = (
            compliance_payload.get("prechecks", {}).get("rule_hits", []) or []
        )
        customer_payload = crew2_results.get("customer_context", {}) or {}
        portfolio_payload = crew2_results.get("portfolio_analysis", {}) or {}
        market_payload = crew2_results.get("market_intelligence", {}) or {}

        alert_payload = normalize_agent_artifact(
            alert_intake.process_accumulated_findings(
            {
                "request_id": state.get("request_id"),
                "portfolio": {
                    "id": portfolio_data.get("id"),
                    "name": portfolio_data.get("name"),
                    "total_value": portfolio_data.get("total_value"),
                },
                "ml_summary": state.get("ml_summary", ""),
                "risk_score": max_risk_score,
                "risk_label": highest_risk_label,
                "hard_block": hard_block,
                "crew1_results": crew1_results,
                "crew2_results": crew2_results,
            }
            ),
            default_agent="AlertIntake",
            primary_text_keys=("analysis", "summary"),
        )
        _emit_llm_thinking(state, "run_full_crew_three", "Alert Intake Agent")
        explanation_input = _build_explanation_input(
            state, alert_payload, crew1_results, crew2_results
        )
        summary = normalize_agent_artifact(
            explanation.summarize_analysis(
                explanation_input,
                "medium",
            ),
            default_agent="Explanation",
            primary_text_keys=("summary", "analysis"),
        )
        _emit_llm_thinking(state, "run_full_crew_three", "Explanation Agent")
        case_data, severity_factors, interactions, decisions = (
            _build_escalation_inputs(
                state,
                alert_payload,
                summary,
                crew1_results,
                crew2_results,
                max_risk_score=max_risk_score,
                hard_block=hard_block,
                compliance_rule_hits=compliance_rule_hits,
            )
        )
        escalation_evaluation = normalize_agent_artifact(
            escalation.evaluate_escalation_need(
                case_data,
                severity_factors,
            ),
            default_agent="EscalationCaseSummary",
            primary_text_keys=("evaluation", "summary", "analysis"),
        )
        _emit_llm_thinking(state, "run_full_crew_three", "Escalation Agent")
        case_summary = normalize_agent_artifact(
            escalation.generate_case_summary(
                {
                    **case_data,
                    "priority_tier": escalation_evaluation.get("priority_tier"),
                    "action_recommendation": escalation_evaluation.get(
                        "action_recommendation"
                    ),
                },
                interactions,
                [
                    *decisions,
                    {
                        "agent": "escalation_evaluation",
                        "action_recommendation": escalation_evaluation.get(
                            "action_recommendation"
                        ),
                        "priority_tier": escalation_evaluation.get("priority_tier"),
                        "structured_output": escalation_evaluation.get(
                            "structured_output", {}
                        ),
                    },
                ],
            ),
            default_agent="EscalationCaseSummary",
            primary_text_keys=("summary", "analysis"),
        )
        _emit_llm_thinking(state, "run_full_crew_three", "Escalation Agent")
        alert_result = _summarize_alert_intake(alert_payload)
        escalation_result = _summarize_escalation(
            escalation_evaluation, case_summary
        )
        state["crew3_results"] = {
            "alert_intake": alert_payload,
            "explanation": summary,
            "escalation_evaluation": escalation_evaluation,
            "escalation_case_summary": case_summary,
        }
        state["crew3_output"] = (
            f"{alert_result}\n\n"
            f"{summary['summary']}\n\n"
            f"{escalation_result}"
        )
        state["crews_run"] = 3
        duration_ms = _elapsed_ms(start)
        _divider_event(
            state,
            node="run_full_crew_three",
            label="Crew 3: Summary and Escalation completed - agents: Alert Intake, Explanation, Escalation",
        )
        _agent_event(
            state,
            node="run_full_crew_three",
            crew="Crew 3: Summary and Escalation",
            name="Alert Intake Agent",
            body=alert_result,
            duration_ms=duration_ms,
            payload=alert_payload,
            evidence_refs=["crew3_results.alert_intake"],
        )
        _agent_event(
            state,
            node="run_full_crew_three",
            crew="Crew 3: Summary and Escalation",
            name="Explanation Agent",
            body=summary["summary"],
            duration_ms=duration_ms,
            payload=summary,
            evidence_refs=[
                "crew1_results.risk_assessment",
                "crew1_results.risk_detection",
                "crew1_results.compliance",
                "crew2_results.portfolio_analysis",
                "crew2_results.market_intelligence",
                "crew2_results.customer_context",
                "crew3_results.alert_intake",
            ],
        )
        _agent_event(
            state,
            node="run_full_crew_three",
            crew="Crew 3: Summary and Escalation",
            name="Escalation Agent",
            body=escalation_result,
            duration_ms=duration_ms,
            payload=case_summary,
            evidence_refs=[
                "crew3_results.escalation_evaluation",
                "crew3_results.escalation_case_summary",
            ],
        )
        return state
    except Exception as exc:
        if is_rate_limit_error(exc):
            state["rate_limited"] = True
            state["crews_run"] = 3
            state["crew3_output"] = "Rate limit exceeded. Analysis incomplete."
            state["crew3_results"] = {}
            _agent_event(
                state,
                node="run_full_crew_three",
                crew="Crew 3: Summary and Escalation",
                name="Summary Crew",
                body=state["crew3_output"],
                duration_ms=_elapsed_ms(start),
                status="rate_limited",
                fallback_reason="rate_limit",
            )
            return state

        state["crew3_output"] = f"Summary Crew failed: {_truncate_error(exc)}"
        state["crews_run"] = 3
        state["crew3_results"] = {}
        _agent_event(
            state,
            node="run_full_crew_three",
            crew="Crew 3: Summary and Escalation",
            name="Summary Crew",
            body=state["crew3_output"],
            duration_ms=_elapsed_ms(start),
            status="failed",
            fallback_reason="crew_failure",
        )
        return state


@traceable(name="langgraph_compile_quick_response", run_type="chain")
def compile_quick_response(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    response = state.get("response") or {}
    response["analysis_trace"] = state.get("analysis_trace", [])
    response["langgraph_route"] = state.get("route", "quick")
    state["response"] = response
    return state


@traceable(name="langgraph_compile_full_response", run_type="chain")
def compile_full_response(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    portfolio = state.get("portfolio") or {}
    ml_summary = state.get("ml_summary", "")
    crews_run = state.get("crews_run", 0)

    if state.get("rate_limited"):
        if crews_run <= 1:
            crew_output = (
                "## 📊 Portfolio Analysis - Rate Limited\n\n"
                "⏰ **Model API Rate Limit Reached**\n\n"
                "**What happened:**\n"
                "The AI analysis system exceeded its current token quota.\n\n"
                "**Your options:**\n"
                "1. **Wait 30-60 seconds** and retry your analysis\n"
                "2. **Increase your model service usage tier** if this happens frequently\n"
                "3. **Switch to a lighter endpoint** - try 'Quick Recommendation' instead\n\n"
                f"**Current Analysis Status:**\n{state.get('crew1_output', '')}\n\n"
                f"### ML Pre-Screening (Always Available)\n{ml_summary}"
            )
        elif crews_run == 2:
            crew_output = (
                "## 📊 Portfolio Analysis - Rate Limited (Crew 2)\n\n"
                "⏰ **Model API Rate Limit Reached**\n\n"
                "**What happened:**\n"
                "The AI analysis system exceeded its token quota during Crew 2.\n\n"
                "**Your options:**\n"
                "1. **Wait 30-60 seconds** and retry your analysis\n"
                "2. **Increase your model service usage tier** if this happens frequently\n"
                "3. **Switch to a lighter endpoint** - try 'Quick Recommendation' instead\n\n"
                "**Completed Analysis:**\n"
                f"- Crew 1 (Risk): {str(state.get('crew1_output', ''))[:100]}...\n"
                f"- Crew 2 (Portfolio): {str(state.get('crew2_output', ''))[:100]}...\n\n"
                f"### ML Pre-Screening (Always Available)\n{ml_summary}"
            )
        else:
            crew_output = (
                "## 📊 Portfolio Analysis - Partial (Rate Limited)\n\n"
                "⏰ **Model API Rate Limit Reached**\n\n"
                "**What happened:**\n"
                "The AI analysis system exceeded its token quota.\n\n"
                "**Your options:**\n"
                "1. **Wait 30-60 seconds** and retry your analysis\n"
                "2. **Increase your model service usage tier** if this happens frequently\n"
                "3. **Switch to a lighter endpoint** - try 'Quick Recommendation' instead\n\n"
                "**Partial Analysis (Completed):**\n"
                f"- Crew 1 (Risk): {str(state.get('crew1_output', ''))[:100]}...\n"
                f"- Crew 2 (Portfolio): {str(state.get('crew2_output', ''))[:100]}...\n"
                f"- Crew 3 (Summary): {str(state.get('crew3_output', ''))[:100]}...\n\n"
                f"### ML Pre-Screening (Always Available)\n{ml_summary}"
            )

        state["response"] = {
            "timestamp": state.get("request_id"),
            "portfolio_id": portfolio.get("id"),
            "crew_output": crew_output,
            "agents_used": 9,
            "crews_run": crews_run,
            "rate_limited": True,
            "langgraph_route": state.get("route", "full"),
            "analysis_trace": state.get("analysis_trace", []),
        }
        return state

    state["response"] = {
        "timestamp": state.get("request_id"),
        "portfolio_id": portfolio.get("id"),
        "crew_output": (
            "## 📊 Multi-Crew Portfolio Analysis (3 Sequential Crews)\n\n"
            f"### Crew 1: Risk Analysis\n{state.get('crew1_output', '')}\n\n"
            f"### Crew 2: Portfolio Analysis\n{state.get('crew2_output', '')}\n\n"
            f"### Crew 3: Summary & Escalation\n{state.get('crew3_output', '')}\n\n"
            f"### ML Pre-Screening\n{ml_summary}"
        ),
        "agents_used": 9,
        "crews_run": 3,
        "rate_limited": False,
        "langgraph_route": state.get("route", "full"),
        "analysis_trace": state.get("analysis_trace", []),
    }
    return state


@traceable(name="langgraph_compile_full_response", run_type="chain")
def compile_full_response(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    portfolio = state.get("portfolio") or {}
    ml_summary = state.get("ml_summary", "")
    crews_run = state.get("crews_run", 0)

    if state.get("rate_limited"):
        if crews_run <= 1:
            crew_output = (
                "## Portfolio Analysis - Rate Limited\n\n"
                "Model API rate limit reached.\n\n"
                "Wait 30-60 seconds and retry, increase the model service quota, "
                "or switch to the quick recommendation path.\n\n"
                f"Current analysis status:\n{state.get('crew1_output', '')}\n\n"
                f"### ML Pre-Screening (Always Available)\n{ml_summary}"
            )
        elif crews_run == 2:
            crew_output = (
                "## Portfolio Analysis - Rate Limited (Crew 2)\n\n"
                "Model API rate limit reached during Crew 2.\n\n"
                "Wait 30-60 seconds and retry, increase the model service quota, "
                "or switch to the quick recommendation path.\n\n"
                "Completed analysis:\n"
                f"- Crew 1 (Risk): {str(state.get('crew1_output', ''))[:100]}...\n"
                f"- Crew 2 (Portfolio): {str(state.get('crew2_output', ''))[:100]}...\n\n"
                f"### ML Pre-Screening (Always Available)\n{ml_summary}"
            )
        else:
            crew_output = (
                "## Portfolio Analysis - Partial (Rate Limited)\n\n"
                "Model API rate limit reached.\n\n"
                "Wait 30-60 seconds and retry, increase the model service quota, "
                "or switch to the quick recommendation path.\n\n"
                "Partial analysis completed:\n"
                f"- Crew 1 (Risk): {str(state.get('crew1_output', ''))[:100]}...\n"
                f"- Crew 2 (Portfolio): {str(state.get('crew2_output', ''))[:100]}...\n"
                f"- Crew 3 (Summary): {str(state.get('crew3_output', ''))[:100]}...\n\n"
                f"### ML Pre-Screening (Always Available)\n{ml_summary}"
            )

        state["response"] = {
            "timestamp": state.get("request_id"),
            "portfolio_id": portfolio.get("id"),
            "crew_output": crew_output,
            "agents_used": 9,
            "crews_run": crews_run,
            "rate_limited": True,
            "langgraph_route": state.get("route", "full"),
            "analysis_trace": state.get("analysis_trace", []),
        }
        return state

    state["response"] = {
        "timestamp": state.get("request_id"),
        "portfolio_id": portfolio.get("id"),
        "crew_output": (
            "## Multi-Crew Portfolio Analysis (3 Sequential Crews)\n\n"
            f"### Crew 1: Risk Analysis\n{state.get('crew1_output', '')}\n\n"
            f"### Crew 2: Portfolio Analysis\n{state.get('crew2_output', '')}\n\n"
            f"### Crew 3: Summary & Escalation\n{state.get('crew3_output', '')}\n\n"
            f"### ML Pre-Screening\n{ml_summary}"
        ),
        "agents_used": 9,
        "crews_run": 3,
        "rate_limited": False,
        "langgraph_route": state.get("route", "full"),
        "analysis_trace": state.get("analysis_trace", []),
    }
    return state


def choose_analysis_route(state: PortfolioAnalysisState) -> str:
    return state.get("route", "quick")


def _serialize_crew_results(crew_results: dict | None) -> dict:
    results = crew_results or {}
    serialized: dict[str, object] = {}
    for key, value in results.items():
        if isinstance(value, dict) and "structured_output" in value:
            serialized[key] = serialize_agent_artifact(value)
        else:
            serialized[key] = value
    return serialized


def _final_action_metadata(state: PortfolioAnalysisState) -> dict[str, object]:
    crew3_results = state.get("crew3_results") or {}
    escalation_eval = crew3_results.get("escalation_evaluation", {}) or {}
    escalation_case = crew3_results.get("escalation_case_summary", {}) or {}
    alert_intake_payload = crew3_results.get("alert_intake", {}) or {}
    evidence_portfolio = (
        escalation_eval.get("evidence_portfolio")
        or escalation_case.get("evidence_portfolio")
        or []
    )
    return {
        "final_action_recommendation": escalation_eval.get("action_recommendation"),
        "final_priority_tier": escalation_eval.get("priority_tier")
        or alert_intake_payload.get("priority_tier"),
        "final_escalation_recommendation": alert_intake_payload.get(
            "escalation_recommendation"
        ),
        "evidence_summary": evidence_portfolio[:3],
        "evidence_portfolio": evidence_portfolio,
    }


@traceable(name="langgraph_compile_quick_response", run_type="chain")
def compile_quick_response(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    response = state.get("response") or {}
    response["analysis_trace"] = state.get("analysis_trace", [])
    response["langgraph_route"] = state.get("route", "quick")
    response["response_contract_version"] = CONTRACT_VERSION
    state["response"] = response
    return state


@traceable(name="langgraph_compile_full_response", run_type="chain")
def compile_full_response(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    portfolio = state.get("portfolio") or {}
    ml_summary = state.get("ml_summary", "")
    crews_run = state.get("crews_run", 0)
    final_action = _final_action_metadata(state)

    if state.get("rate_limited"):
        if crews_run <= 1:
            crew_output = (
                "## Portfolio Analysis - Rate Limited\n\n"
                "Model API rate limit reached.\n\n"
                "Wait 30-60 seconds and retry, increase the model service quota, "
                "or switch to the quick recommendation path.\n\n"
                f"Current analysis status:\n{state.get('crew1_output', '')}\n\n"
                f"### ML Pre-Screening (Always Available)\n{ml_summary}"
            )
        elif crews_run == 2:
            crew_output = (
                "## Portfolio Analysis - Rate Limited (Crew 2)\n\n"
                "Model API rate limit reached during Crew 2.\n\n"
                "Wait 30-60 seconds and retry, increase the model service quota, "
                "or switch to the quick recommendation path.\n\n"
                "Completed analysis:\n"
                f"- Crew 1 (Risk): {str(state.get('crew1_output', ''))[:100]}...\n"
                f"- Crew 2 (Portfolio): {str(state.get('crew2_output', ''))[:100]}...\n\n"
                f"### ML Pre-Screening (Always Available)\n{ml_summary}"
            )
        else:
            crew_output = (
                "## Portfolio Analysis - Partial (Rate Limited)\n\n"
                "Model API rate limit reached.\n\n"
                "Wait 30-60 seconds and retry, increase the model service quota, "
                "or switch to the quick recommendation path.\n\n"
                "Partial analysis completed:\n"
                f"- Crew 1 (Risk): {str(state.get('crew1_output', ''))[:100]}...\n"
                f"- Crew 2 (Portfolio): {str(state.get('crew2_output', ''))[:100]}...\n"
                f"- Crew 3 (Summary): {str(state.get('crew3_output', ''))[:100]}...\n\n"
                f"### ML Pre-Screening (Always Available)\n{ml_summary}"
            )

        state["response"] = {
            "timestamp": state.get("request_id"),
            "portfolio_id": portfolio.get("id"),
            "crew_output": crew_output,
            "agents_used": 9,
            "crews_run": crews_run,
            "rate_limited": True,
            "langgraph_route": state.get("route", "full"),
            "analysis_trace": state.get("analysis_trace", []),
            "crew1_results": _serialize_crew_results(state.get("crew1_results")),
            "crew2_results": _serialize_crew_results(state.get("crew2_results")),
            "crew3_results": _serialize_crew_results(state.get("crew3_results")),
            "response_contract_version": CONTRACT_VERSION,
            **final_action,
        }
        return state

    state["response"] = {
        "timestamp": state.get("request_id"),
        "portfolio_id": portfolio.get("id"),
        "crew_output": (
            "## Multi-Crew Portfolio Analysis (3 Sequential Crews)\n\n"
            f"### Crew 1: Risk Analysis\n{state.get('crew1_output', '')}\n\n"
            f"### Crew 2: Portfolio Analysis\n{state.get('crew2_output', '')}\n\n"
            f"### Crew 3: Summary & Escalation\n{state.get('crew3_output', '')}\n\n"
            f"### ML Pre-Screening\n{ml_summary}"
        ),
        "agents_used": 9,
        "crews_run": 3,
        "rate_limited": False,
        "langgraph_route": state.get("route", "full"),
        "analysis_trace": state.get("analysis_trace", []),
        "crew1_results": _serialize_crew_results(state.get("crew1_results")),
        "crew2_results": _serialize_crew_results(state.get("crew2_results")),
        "crew3_results": _serialize_crew_results(state.get("crew3_results")),
        "response_contract_version": CONTRACT_VERSION,
        **final_action,
    }
    return state


def run_full_crews_parallel(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    """Compatibility alias for older imports and tests."""
    return run_full_crews(state)
