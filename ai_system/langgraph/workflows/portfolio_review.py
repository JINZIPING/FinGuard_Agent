"""LangGraph workflow for legacy-aligned portfolio review."""

from ai_system.langgraph.nodes import (
    choose_analysis_route,
    compile_full_response,
    compile_quick_response,
    ingest_request,
    run_full_crews_parallel,
    run_quick_recommendation,
)
from ai_system.langgraph.state import PortfolioAnalysisState

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover
    END = "__end__"
    StateGraph = None


class _FallbackCompiledGraph:
    """Minimal sequential fallback used when langgraph is unavailable."""

    def invoke(self, state: PortfolioAnalysisState) -> PortfolioAnalysisState:
        next_state = ingest_request(dict(state))
        route = choose_analysis_route(next_state)
        if route == "quick":
            next_state = run_quick_recommendation(next_state)
            next_state = compile_quick_response(next_state)
            return next_state
        next_state = run_full_crew_one(next_state)
        next_state = run_full_crew_two(next_state)
        next_state = run_full_crew_three(next_state)
        next_state = compile_full_response(next_state)
        return next_state


def build_portfolio_review_graph():
    if StateGraph is None:
        return _FallbackCompiledGraph()

    graph = StateGraph(PortfolioAnalysisState)
    graph.add_node("ingest_request", ingest_request)
    graph.add_node("run_quick_recommendation", run_quick_recommendation)
    graph.add_node("compile_quick_response", compile_quick_response)
    graph.add_node("run_full_crews_parallel", run_full_crews_parallel)
    graph.add_node("compile_full_response", compile_full_response)

    graph.set_entry_point("ingest_request")
    graph.add_conditional_edges(
        "ingest_request",
        choose_analysis_route,
        {
            "quick": "run_quick_recommendation",
            "full": "run_full_crews_parallel",
        },
    )
    graph.add_edge("run_quick_recommendation", "compile_quick_response")
    graph.add_edge("compile_quick_response", END)
    graph.add_edge("run_full_crews_parallel", "compile_full_response")
    graph.add_edge("compile_full_response", END)

    return graph.compile()
