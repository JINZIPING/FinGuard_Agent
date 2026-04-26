"""LangGraph nodes for portfolio review with legacy-compatible semantics."""

from __future__ import annotations

from time import perf_counter

from ai_system.app.agents import (
    explanation_agent as explanation,
    portfolio_analysis_agent as portfolio,
    risk_assessment_agent as risk,
)
from ai_system.app.analysis_utils import ml_score_transactions
from ai_system.app.llm import is_rate_limit_error
from ai_system.langgraph.state import PortfolioAnalysisState


def _truncate_error(exc: Exception) -> str:
    return str(exc)[:200]


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _append_trace(state: PortfolioAnalysisState, event: dict) -> None:
    trace = state.setdefault("analysis_trace", [])
    trace.append({"sequence": len(trace) + 1, **event})


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
) -> None:
    _append_trace(
        state,
        {
            "type": "agent",
            "node": node,
            "crew": crew,
            "name": name,
            "status": status,
            "duration_ms": duration_ms,
            "body": body,
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
            "agent_name": agent_name,
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


def _compliance_snapshot(transactions: list[dict]) -> str:
    findings: list[str] = []
    unknown_types = sorted(
        {
            (txn.get("type") or "").lower()
            for txn in transactions
            if (txn.get("type") or "").lower() not in {"buy", "sell", "dividend", ""}
        }
    )
    if unknown_types:
        findings.append(
            f"Unsupported transaction types seen: {', '.join(unknown_types)}."
        )
    if len(transactions) >= 20:
        findings.append(
            "Transaction volume is elevated and may merit reporting-threshold review."
        )
    if not findings:
        findings.append(
            "No immediate compliance concern was found in the quick policy scan."
        )
    return " ".join(findings)


def _market_snapshot(symbols: list[str]) -> str:
    if not symbols:
        return "No active symbols were available for a focused market sentiment pass."
    return (
        f"Market context was summarized for {', '.join(symbols[:5])}. "
        "Use the dedicated sentiment endpoint for a deeper symbol-level read."
    )


def _customer_snapshot(portfolio_data: dict, transactions: list[dict]) -> str:
    return (
        f"Customer context: portfolio '{portfolio_data.get('name', 'Unnamed')}' "
        f"has {len(portfolio_data.get('assets', []))} assets and {len(transactions)} recent transactions. "
        "Current behavior appears consistent with routine portfolio activity."
    )


def _alert_snapshot(state: PortfolioAnalysisState) -> str:
    ml_summary = state.get("ml_summary", "")
    if "High/Critical: 0" in ml_summary:
        return "Alert intake found no urgent escalation signal from the ML pre-screening summary."
    if ml_summary:
        return "Alert intake flagged the portfolio for analyst review because elevated ML risk indicators were present."
    return "Alert intake had limited machine-scored context and recommends normal analyst discretion."


def _escalation_snapshot(state: PortfolioAnalysisState) -> str:
    ml_summary = state.get("ml_summary", "")
    if "High/Critical: 0" in ml_summary:
        return "Escalation path: remain in standard monitoring unless new risk signals appear."
    return "Escalation path: queue for human review if related alerts or repeated high-risk transactions continue."


def ingest_request(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    state.setdefault("findings", [])
    state.setdefault("errors", [])
    state.setdefault("analysis_trace", [])
    state.setdefault("crews_run", 0)
    state.setdefault("rate_limited", False)
    state["route"] = state.get("route") or (
        "quick" if len(state.get("transactions", [])) < 10 else "full"
    )

    portfolio_data = state.get("portfolio") or {}
    transactions = state.get("transactions") or []
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
    )
    return state


def run_full_crew_one(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    if state.get("rate_limited"):
        return state

    portfolio_data = state.get("portfolio") or {}
    transactions = state.get("transactions") or []
    start = perf_counter()

    try:
        ml_scores = [risk.score_transaction(txn) for txn in transactions[:10]]
        risk_assessment = risk.assess_portfolio_risk(
            portfolio_data,
            {"volatility": "current market conditions"},
        )
        fraud_assessment = risk.detect_fraud_risk(
            transactions, portfolio_data, ml_scores
        )
        compliance_result = _compliance_snapshot(transactions)
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
        )
        _agent_event(
            state,
            node="run_full_crew_one",
            crew="Crew 1: Risk Analysis",
            name="Risk Detection Agent",
            body=fraud_assessment["assessment"],
            duration_ms=duration_ms,
        )
        _agent_event(
            state,
            node="run_full_crew_one",
            crew="Crew 1: Risk Analysis",
            name="Compliance Agent",
            body=compliance_result,
            duration_ms=duration_ms,
        )
        return state
    except Exception as exc:
        if is_rate_limit_error(exc):
            state["rate_limited"] = True
            state["crews_run"] = 1
            state["crew1_output"] = (
                "Rate limit exceeded. Please wait 30 seconds and try again."
            )
            _agent_event(
                state,
                node="run_full_crew_one",
                crew="Crew 1: Risk Analysis",
                name="Risk Analysis Crew",
                body=state["crew1_output"],
                duration_ms=_elapsed_ms(start),
                status="rate_limited",
            )
            return state

        state["crew1_output"] = f"Risk Analysis failed: {_truncate_error(exc)}"
        state["crews_run"] = 1
        _agent_event(
            state,
            node="run_full_crew_one",
            crew="Crew 1: Risk Analysis",
            name="Risk Analysis Crew",
            body=state["crew1_output"],
            duration_ms=_elapsed_ms(start),
            status="failed",
        )
        return state


def run_full_crew_two(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    if state.get("rate_limited"):
        return state

    portfolio_data = state.get("portfolio") or {}
    transactions = state.get("transactions") or []
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
        portfolio_analysis = portfolio.analyze_portfolio(portfolio_data)
        market_result = _market_snapshot(symbols or fallback_symbols)
        customer_result = _customer_snapshot(portfolio_data, transactions)
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
            agent_name="Portfolio Analyst",
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
            name="Portfolio Analyst",
            body=portfolio_analysis["analysis"],
            duration_ms=duration_ms,
        )
        _agent_event(
            state,
            node="run_full_crew_two",
            crew="Crew 2: Portfolio Analysis",
            name="Market Intelligence Agent",
            body=market_result,
            duration_ms=duration_ms,
        )
        _agent_event(
            state,
            node="run_full_crew_two",
            crew="Crew 2: Portfolio Analysis",
            name="Customer Context Agent",
            body=customer_result,
            duration_ms=duration_ms,
        )
        return state
    except Exception as exc:
        if is_rate_limit_error(exc):
            state["rate_limited"] = True
            state["crews_run"] = 2
            state["crew2_output"] = "Rate limit exceeded. Skipping remaining crews."
            _agent_event(
                state,
                node="run_full_crew_two",
                crew="Crew 2: Portfolio Analysis",
                name="Portfolio Analysis Crew",
                body=state["crew2_output"],
                duration_ms=_elapsed_ms(start),
                status="rate_limited",
            )
            return state

        state["crew2_output"] = f"Portfolio Analysis failed: {_truncate_error(exc)}"
        state["crews_run"] = 2
        _agent_event(
            state,
            node="run_full_crew_two",
            crew="Crew 2: Portfolio Analysis",
            name="Portfolio Analysis Crew",
            body=state["crew2_output"],
            duration_ms=_elapsed_ms(start),
            status="failed",
        )
        return state


def run_full_crew_three(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    if state.get("rate_limited"):
        return state

    portfolio_data = state.get("portfolio") or {}
    start = perf_counter()

    try:
        summary = explanation.summarize_analysis(
            {
                "crew_1": state.get("crew1_output", ""),
                "crew_2": state.get("crew2_output", ""),
                "portfolio": portfolio_data.get("name"),
            },
            "medium",
        )
        alert_result = _alert_snapshot(state)
        escalation_result = _escalation_snapshot(state)
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
        )
        _agent_event(
            state,
            node="run_full_crew_three",
            crew="Crew 3: Summary and Escalation",
            name="Explanation Agent",
            body=summary["summary"],
            duration_ms=duration_ms,
        )
        _agent_event(
            state,
            node="run_full_crew_three",
            crew="Crew 3: Summary and Escalation",
            name="Escalation Agent",
            body=escalation_result,
            duration_ms=duration_ms,
        )
        return state
    except Exception as exc:
        if is_rate_limit_error(exc):
            state["rate_limited"] = True
            state["crews_run"] = 3
            state["crew3_output"] = "Rate limit exceeded. Analysis incomplete."
            _agent_event(
                state,
                node="run_full_crew_three",
                crew="Crew 3: Summary and Escalation",
                name="Summary Crew",
                body=state["crew3_output"],
                duration_ms=_elapsed_ms(start),
                status="rate_limited",
            )
            return state

        state["crew3_output"] = f"Summary Crew failed: {_truncate_error(exc)}"
        state["crews_run"] = 3
        _agent_event(
            state,
            node="run_full_crew_three",
            crew="Crew 3: Summary and Escalation",
            name="Summary Crew",
            body=state["crew3_output"],
            duration_ms=_elapsed_ms(start),
            status="failed",
        )
        return state


def compile_quick_response(state: PortfolioAnalysisState) -> PortfolioAnalysisState:
    response = state.get("response") or {}
    response["analysis_trace"] = state.get("analysis_trace", [])
    response["langgraph_route"] = state.get("route", "quick")
    state["response"] = response
    return state


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
            "## 📊 Multi-Crew Portfolio Analysis (3 Parallel Crews)\n\n"
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
