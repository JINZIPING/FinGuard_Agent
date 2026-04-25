# FinGuard API Contract

Last updated: 2026-04-26

This document is the stable frontend/backend contract. Keep response envelopes backward-compatible and prefer additive changes over renames.

## Base URLs

```text
Local backend dev:      http://localhost:5000
Docker backend:         http://localhost:15050
Docker frontend:        http://localhost:13000
Docker ai_system:       http://localhost:18000
```

Frontend builds inject the backend origin through:

```text
REACT_APP_API_BASE_URL
```

## Operational Modes

### Backend auth

- `AUTH_ENFORCED=false`
  - default demo mode
  - case, audit, and SAR flows use the default system identity
- `AUTH_ENFORCED=true`
  - bearer token required for auth-protected routes
  - set a strong `JWT_SECRET`

### AI response mode

- `AI_RESPONSE_MODE=live`
  - uses OpenAI
- `AI_RESPONSE_MODE=mock`
  - deterministic offline/demo mode
  - recommended for CI and classroom demos

## Frontend-Used Endpoints

### Health

```text
GET /health
GET /api/health
```

Response:

```json
{ "status": "healthy", "timestamp": "2026-04-26T00:00:00" }
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
      "user_id": "customer_demo_001",
      "name": "FinGuard Demo Portfolio",
      "total_value": 250000,
      "cash_balance": 250000,
      "created_at": "2026-04-26T00:00:00+00:00",
      "updated_at": "2026-04-26T00:00:00+00:00"
    }
  ]
}
```

`POST /api/portfolios/{portfolio_id}/analyze` response:

```json
{
  "timestamp": "2026-04-26T00:00:00+00:00",
  "portfolio_id": 1,
  "crew_output": "Final analysis text",
  "agents_used": 9,
  "crews_run": 3,
  "rate_limited": false,
  "langgraph_route": "full",
  "analysis_trace": [
    {
      "sequence": 1,
      "type": "agent",
      "node": "run_full_crew_one",
      "crew": "Crew 1: Risk Analysis",
      "name": "Risk Detection Agent",
      "status": "completed",
      "duration_ms": 1200,
      "body": "Agent output"
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

### Transactions and Recommendations

```text
POST /api/transaction/score-risk
POST /api/transaction/get-ai-insights
POST /api/portfolios/{portfolio_id}/quick-recommendation
POST /api/portfolios/{portfolio_id}/recommendation
```

## Case / Compliance Endpoints

```text
GET /api/cases
GET /api/cases/{case_id}
POST /api/cases
POST /api/cases/{case_id}/assign
POST /api/cases/{case_id}/notes
POST /api/cases/{case_id}/transition
POST /api/cases/{case_id}/analyze
GET /api/cases/{case_id}/customer-360
GET /api/audit/logs
GET /api/audit/verify
GET /api/sar/{case_id}.json
GET /api/sar/{case_id}.pdf
```

## Demo Seed Workflow

The repo includes a deterministic CLI seed path:

```bash
python scripts/seed_demo_data.py --reset
```

This is intentionally a script-based workflow, not a public demo-only API route.

## Compatibility Rules

- keep response envelopes stable: `portfolios`, `assets`, `transactions`, `alerts`, `items`, `results`
- prefer plural route aliases in new frontend code
- add fields instead of renaming or deleting fields
- frontend should tolerate both `{ "error": "..." }` and `{ "detail": "..." }`
