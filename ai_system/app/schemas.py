"""Shared request/response schemas for ai_system."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AssetSnapshot(BaseModel):
    symbol: str | None = None
    name: str | None = None
    quantity: float | None = None
    current_price: float | None = None
    purchase_price: float | None = None
    asset_type: str | None = None


class PortfolioSnapshot(BaseModel):
    id: int | None = None
    name: str | None = None
    total_value: float = 0
    cash_balance: float = 0
    assets: list[AssetSnapshot] = Field(default_factory=list)


class TransactionSnapshot(BaseModel):
    id: int | None = None
    symbol: str | None = None
    type: str | None = None
    quantity: float | None = None
    price: float | None = None
    timestamp: str | None = None


class PortfolioReviewRequest(BaseModel):
    portfolio: PortfolioSnapshot
    transactions: list[TransactionSnapshot] = Field(default_factory=list)
    mode: str = "quick"


class MarketSentimentRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    detail_level: str = "short"


class MarketRecommendationRequest(BaseModel):
    symbol: str
    portfolio_size: float = 0
    risk_profile: str = "moderate"
    detail_level: str = "short"


class TransactionRiskRequest(BaseModel):
    transaction: dict[str, Any] = Field(default_factory=dict)
    customer_profile: dict[str, Any] = Field(default_factory=dict)


class TransactionInsightRequest(BaseModel):
    transaction: dict[str, Any]
    score: float = 50
    factors: dict[str, Any] = Field(default_factory=dict)
