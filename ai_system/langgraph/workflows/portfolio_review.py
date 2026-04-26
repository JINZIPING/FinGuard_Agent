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


def build_portfolio_review_graph():
    if StateGraph is None:
        raise ImportError("langgraph is not installed yet")

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
