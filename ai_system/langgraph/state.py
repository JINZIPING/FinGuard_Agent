"""Shared state objects for LangGraph workflows."""

from typing import Any, Literal, TypedDict

from ai_system.langgraph.contracts import Crew1Results, Crew2Results, Crew3Results


class PortfolioAnalysisState(TypedDict, total=False):
    request_id: str
    portfolio: dict[str, Any]
    transactions: list[dict[str, Any]]
    route: Literal["quick", "full"]
    portfolio_summary: str
    transaction_summary: str
    ml_summary: str
    customer_context_seed: dict[str, Any]
    crew1_output: str
    crew1_results: Crew1Results
    crew2_output: str
    crew2_results: Crew2Results
    crew3_output: str
    crew3_results: Crew3Results
    crews_run: int
    rate_limited: bool
    findings: list[str]
    response: dict[str, Any]
    errors: list[str]
    analysis_trace: list[dict[str, Any]]
