"""Minimal ai_system service with internal agent modules and LangGraph scaffold."""

from typing import Any

from fastapi import FastAPI

from ai_system.app.agents import (
    compliance_agent as compliance,
    explanation_agent as explanation,
    market_intelligence_agent as market,
    portfolio_analysis_agent as portfolio,
    risk_assessment_agent as risk,
)
from ai_system.app.llm import response_mode
from ai_system.app.orchestrator import portfolio_review
from ai_system.app.schemas import (
    MarketRecommendationRequest,
    MarketSentimentRequest,
    PortfolioReviewRequest,
    TransactionInsightRequest,
    TransactionRiskRequest,
)


app = FastAPI(title="FinGuard AI System")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "response_mode": response_mode()}


@app.post("/agents/risk/invoke")
def invoke_risk_agent(payload: PortfolioReviewRequest) -> dict[str, Any]:
    return risk.invoke(
        payload.portfolio.model_dump(),
        [txn.model_dump() for txn in payload.transactions],
        payload.mode,
    )


@app.post("/agents/portfolio/invoke")
def invoke_portfolio_agent(payload: PortfolioReviewRequest) -> dict[str, Any]:
    return portfolio.invoke(
        payload.portfolio.model_dump(),
        [txn.model_dump() for txn in payload.transactions],
        payload.mode,
    )


@app.post("/agents/compliance/invoke")
def invoke_compliance_agent(payload: PortfolioReviewRequest) -> dict[str, Any]:
    return compliance.invoke(
        payload.portfolio.model_dump(),
        [txn.model_dump() for txn in payload.transactions],
        payload.mode,
    )


@app.post("/orchestrate/portfolio-review")
def orchestrate_portfolio_review(payload: PortfolioReviewRequest) -> dict[str, Any]:
    return portfolio_review(
        payload.portfolio.model_dump(),
        [txn.model_dump() for txn in payload.transactions],
        payload.mode,
    )


@app.post("/market/sentiment")
def get_market_sentiment(payload: MarketSentimentRequest) -> dict[str, Any]:
    return market.analyze_sentiment(payload.symbols)


@app.post("/market/recommendation")
def get_market_recommendation(payload: MarketRecommendationRequest) -> dict[str, Any]:
    return market.generate_recommendation(
        payload.symbol, payload.portfolio_size, payload.risk_profile
    )


@app.post("/risk/score-transaction")
def score_transaction(payload: TransactionRiskRequest) -> dict[str, Any]:
    return risk.score_transaction(payload.transaction, payload.customer_profile)


@app.post("/explanation/transaction-insights")
def get_transaction_insights(payload: TransactionInsightRequest) -> dict[str, Any]:
    return explanation.explain_transaction_risk(
        payload.transaction, payload.score, payload.factors
    )
