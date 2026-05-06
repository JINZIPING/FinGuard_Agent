# FinGuard Comprehensive Guide

Last updated: 2026-05-06

## 1. What FinGuard Is

FinGuard is a fraud and portfolio risk investigation tool. It combines the React frontend, a FastAPI backend, and a LangGraph-based AI system with internal agents.

The product is designed for:

- portfolio and transaction review
- fraud and risk analysis
- market sentiment checks
- case workflow
- audit and SAR export
- explainable multi-agent AI output

## 2. Architecture

```text
React Frontend
  -> FastAPI Backend
      -> SQLite persistence
      -> AI System over HTTP
          -> LangGraph workflow
          -> Internal agents
          -> OpenAI model adapter
          -> ML/rules risk adapter
```

Service responsibilities:

- `frontend`: primary analyst UI, delivered as a standalone React app.
- `backend`: stable API, persistence, auth, cases, audit, SAR, and AI proxying.
- `ai_system`: model calls, LangGraph orchestration, agent strategy, and trace metadata.

## 3. Main Workflow

1. User opens the frontend.
2. User selects a portfolio in AI Analysis.
3. Frontend calls backend portfolio endpoints.
4. Frontend calls `POST /api/portfolios/{id}/analyze`.
5. Backend builds a normalized payload and calls `ai_system`.
6. AI system runs LangGraph and internal agents.
7. AI system returns final output, structured crew result blocks, top-level recommendation metadata, and `analysis_trace`.
8. Frontend renders the real trace and final analysis.

## 4. Internal Agents

Current agent list:

- Alert Intake
- Customer Context
- Risk Assessment
- Risk Detection
- Explanation
- Escalation Summary
- Portfolio Analysis
- Market Intelligence
- Compliance

The agents are code-level modules inside `ai_system`, not separate services.

## 5. LangGraph Flow

Current portfolio review graph:

```text
ingest_request
  -> quick: run_quick_recommendation
  -> full: run_full_crew_one
       -> run_full_crew_two
       -> run_full_crew_three
       -> compile_full_response
```

Returned trace events include:

- `sequence`
- `contract_version`
- `type`
- `node`
- `crew`
- `agent`
- `name`
- `status`
- `duration_ms`
- `body`
- `structured_summary`
- `severity`
- `confidence`
- `evidence_refs`
- `fallback_used`
- `fallback_reason`
- `rate_limited`
- `data_basis`

The trace is real after completion. It is not yet streamed live while the request is running.

## 6. Running Locally

Create `ai_system/.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.4-mini
OPENAI_REASONING_EFFORT=medium
```

Run:

```bash
docker compose up --build
```

Open:

```text
http://localhost:13000
```

Service URLs:

- Frontend: `http://localhost:13000`
- Backend: `http://localhost:15050`
- AI system: `http://localhost:18000`

## 7. Frontend Configuration

The React frontend injects the backend base URL at build time through:

```text
REACT_APP_API_BASE_URL=http://localhost:15050
```

For local `npm start`, the frontend falls back to `/api` and uses the React dev proxy.

## 8. Backend Configuration

Important environment variables:

```text
AI_SYSTEM_URL=http://ai_system:8000
AI_SYSTEM_TIMEOUT_SECONDS=90
CORS_ORIGINS=http://localhost:13000,http://localhost:3000
AUTH_ENFORCED=false
JWT_SECRET=<set-in-production>
BACKEND_DB_PATH=./data/backend.db
```

Production notes:

- Set `AUTH_ENFORCED=true`.
- Set a strong `JWT_SECRET`.
- Configure `CORS_ORIGINS` to the deployed frontend origin.
- Use durable storage or a managed database for cloud persistence.

## 9. AI System Configuration

Important environment variables:

```text
OPENAI_API_KEY=<required>
OPENAI_MODEL=gpt-5.4-mini
OPENAI_REASONING_EFFORT=medium
```

If trained ML model files are unavailable, risk scoring falls back to rule-based behavior where supported.

## 10. Key API Groups

See `api.md` for the concise contract.

Main frontend-used endpoints:

- `GET /api/portfolios`
- `GET /api/portfolios/{id}`
- `GET /api/portfolios/{id}/assets`
- `GET /api/portfolios/{id}/transactions`
- `POST /api/portfolios/{id}/analyze`
- `GET /api/symbols`
- `GET /api/sentiment?symbols=AAPL,MSFT`

Other backend capabilities:

- auth
- alerts
- transaction risk scoring
- recommendations
- cases
- audit verification
- SAR JSON/PDF export
- search

## 11. Deployment

Current GitHub Actions workflow:

```text
.github/workflows/deploy-backend.yml
```

It:

- triggers on push to `main`
- builds `backend/Dockerfile`
- uses `linux/amd64`
- tags with `${{ github.sha }}`
- pushes to `finguardacr.azurecr.io/finguard-backend`
- updates Azure Container App `finguard-backend`

Required GitHub secrets:

- `AZURE_CREDENTIALS`
- `AZURE_RESOURCE_GROUP`

Current deployment gap:

- frontend and `ai_system` do not yet have matching CI/CD workflows.

## 12. Current Limitations

- Some frontend flows currently wait for direct JSON responses because backend SSE endpoints are not implemented yet.
- Agent trace is returned after completion, not streamed live.
- SQLite is demo-friendly but needs a durable production plan.
- Backend-only CI/CD is not enough for full cloud deployment.

## 13. Recommended Next Steps

1. Add SSE streaming endpoints so the frontend can show live thinking instead of final-only responses.
2. Complete a first-class auth flow for cases instead of manual bearer token pasting.
3. Break the embedded frontend shell into native React components over time.
4. Add CI/CD for frontend and `ai_system`.
5. Move cloud persistence to durable storage.
