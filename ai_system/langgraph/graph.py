"""Primary compiled graph entrypoint for LangGraph tooling."""

from ai_system.langgraph import nodes
from ai_system.langgraph.workflows.portfolio_review import build_portfolio_review_graph


class _FallbackGraph:
    """Minimal local runner used when langgraph is unavailable in the environment."""

    def invoke(self, state: dict) -> dict:
        next_state = dict(state)
        next_state = nodes.ingest_request(next_state)
        route = nodes.choose_analysis_route(next_state)
        if route == "quick":
            next_state = nodes.run_quick_recommendation(next_state)
            return nodes.compile_quick_response(next_state)

        next_state = nodes.run_full_crews_parallel(next_state)
        return nodes.compile_full_response(next_state)


try:
    graph = build_portfolio_review_graph()
except ImportError:  # pragma: no cover - exercised in dependency-light test envs
    graph = _FallbackGraph()
