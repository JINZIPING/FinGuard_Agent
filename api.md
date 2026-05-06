# FinGuard API Contract

Last updated: 2026-05-06

This is the concise frontend/backend contract. Keep it updated when route paths, payloads, auth, or response envelopes change.

## Base URLs

```text
Local backend dev:      http://localhost:5000
Docker backend:         http://localhost:15050
Docker frontend:        http://localhost:13000
Cloud backend:          https://<finguard-backend-url>
```

Frontend builds can inject the backend base URL through:

```text
REACT_APP_API_BASE_URL
```

Local React development can also fall back to same-origin `/api` via the dev proxy.

Backend CORS must include the deployed frontend origin:

```text
CORS_ORIGINS=https://<frontend-url>
```

## Conventions

- JSON request/response bodies unless noted otherwise.
- Send `Content-Type: application/json`.
- Auth header: `Authorization: Bearer <token>`.
- Error shape may be `{ "error": "..." }` or `{ "detail": "..." }`.

Demo mode:

- `AUTH_ENFORCED=false` allows default system identity.
- Production should set `AUTH_ENFORCED=true` and a strong `JWT_SECRET`.

## Frontend-Used Endpoints

### Health

```text
GET /health
GET /api/health
```

Response:

```json
{ "status": "healthy", "timestamp": "2026-04-25T00:00:00" }
```

### Portfolios

```text
GET /api/portfolios
GET /api/portfolios/{portfolio_id}
GET /api/portfolios/{portfolio_id}/assets
GET /api/portfolios/{portfolio_id}/transactions
POST /api/portfolios/{portfolio_id}/analyze
```

`GET /api/portfolios` response:

```json
{
  "portfolios": [
    {
      "id": 1,
      "user_id": "user_123",
      "name": "Demo Portfolio",
      "total_value": 10000,
      "cash_balance": 5000,
      "created_at": "2026-04-25T00:00:00",
      "updated_at": "2026-04-25T00:00:00"
    }
  ]
}
```

`POST /api/portfolios/{portfolio_id}/analyze` response:

```json
{
  "timestamp": "2026-04-25T00:00:00",
  "portfolio_id": 1,
  "crew_output": "Final analysis text",
  "agents_used": 9,
  "crews_run": 3,
  "rate_limited": false,
  "langgraph_route": "full",
  "response_contract_version": "2026-05-06",
  "final_action_recommendation": "Report",
  "final_priority_tier": "P1",
  "final_escalation_recommendation": "Yes",
  "evidence_summary": ["Risk score: 88", "AML review"],
  "evidence_portfolio": ["Risk score: 88", "AML review"],
  "crew1_results": {
    "risk_assessment": {
      "agent": "RiskAssessment",
      "timestamp": "2026-05-06T00:00:00+00:00",
      "structured_output": {
        "summary": "Risk assessment summary.",
        "severity": "high",
        "confidence": "medium",
        "key_factors": ["Liquidity concentration"],
        "recommended_actions": ["Review concentration."],
        "follow_up": ["Monitor."],
        "raw_text": "Risk assessment summary."
      }
    }
  },
  "crew2_results": {},
  "crew3_results": {},
  "analysis_trace": [
    {
      "sequence": 1,
      "contract_version": "2026-05-06",
      "type": "agent",
      "node": "run_full_crew_one",
      "crew": "Crew 1: Risk Analysis",
      "agent": "Risk Detection Agent",
      "name": "Risk Detection Agent",
      "status": "completed",
      "duration_ms": 1200,
      "body": "Agent output",
      "structured_summary": "Fraud review summary.",
      "severity": "medium",
      "confidence": "high",
      "evidence_refs": ["crew1_results.risk_detection"],
      "fallback_used": false,
      "fallback_reason": null,
      "rate_limited": false,
      "data_basis": null
    }
  ]
}
```

### Symbols and Sentiment

```text
GET /api/symbols
GET /api/symbols/sectors
GET /api/sentiment?symbols=AAPL,MSFT
GET /api/sentiment/{symbol}
```

`GET /api/symbols` response:

```json
{
  "symbols": [
    { "symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology" }
  ],
  "default_symbols": ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "NVDA"]
}
```

Sentiment response:

```json
{
  "agent": "MarketIntelligence",
  "symbols": ["AAPL", "MSFT"],
  "sentiment_analysis": "Text analysis"
}
```

## Other Backend Endpoints

Auth:

```text
POST /api/auth/register
POST /api/auth/login
GET /api/auth/me
```

Portfolio mutation:

```text
POST /api/portfolios
POST /api/portfolio/{portfolio_id}/asset
POST /api/portfolios/{portfolio_id}/transactions
POST /api/portfolios/{portfolio_id}/quick-recommendation
POST /api/portfolios/{portfolio_id}/recommendation
POST /api/portfolio/{portfolio_id}/alert
GET /api/portfolios/{portfolio_id}/alerts
```

Transaction utilities:

```text
POST /api/transaction/score-risk
POST /api/transaction/get-ai-insights
```

Cases:

```text
GET /api/cases
GET /api/cases/{case_id}
POST /api/cases
POST /api/cases/{case_id}/assign
POST /api/cases/{case_id}/notes
POST /api/cases/{case_id}/transition
POST /api/cases/{case_id}/analyze
GET /api/cases/{case_id}/customer-360
```

Audit and SAR:

```text
GET /api/audit/logs
GET /api/audit/verify
GET /api/sar/{case_id}.json
GET /api/sar/{case_id}.pdf
```

Search:

```text
POST /api/search/analyses
POST /api/search/risks
POST /api/search/market
```

## Compatibility Rules

- Prefer plural routes in new frontend code, for example `/api/portfolios/{id}`.
- Keep response envelopes stable: `portfolios`, `assets`, `transactions`, `alerts`, `items`, `results`.
- Add fields instead of renaming existing fields.
- Frontend should handle both `error` and `detail` error responses.
- Do not hardcode localhost URLs in source pages.
