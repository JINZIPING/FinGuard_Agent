# FinGuard

FinGuard is an AI-assisted fraud and portfolio risk investigation system.

```text
Frontend (React analyst UI)
  -> Backend (FastAPI)
      -> AI System (FastAPI + LangGraph)
          -> Internal agent modules
```

## Services

- `frontend`: primary React frontend for the analyst UI.
- `backend`: FastAPI business API, persistence, auth, cases, audit, SAR, and API compatibility.
- `ai_system`: FastAPI AI service with LangGraph orchestration, OpenAI adapter, ML/rules risk adapter, and internal agents.

## Current Features

- Portfolio APIs and AI analysis flow.
- AI Analysis UI with portfolio dropdown.
- LangGraph-backed multi-agent review.
- Returned `analysis_trace` with node, crew, agent, status, duration, structured summary, evidence refs, and fallback metadata.
- Structured `crew1_results`, `crew2_results`, and `crew3_results` in the final response.
- Top-level final recommendation, priority tier, and evidence summary in the final response.
- Market sentiment analysis.
- Case, audit, SAR, search, auth, transaction, alert, and recommendation APIs.
- Docker Compose local stack.
- Backend GitHub Actions deployment to Azure Container Apps.

## Internal Agents

- Alert Intake
- Customer Context
- Risk Assessment
- Risk Detection
- Explanation
- Escalation Summary
- Portfolio Analysis
- Market Intelligence
- Compliance

## Run Locally With Docker

Create `ai_system/.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.4-mini
OPENAI_REASONING_EFFORT=medium
```

Start the stack:

```bash
docker compose up --build
```

URLs:

- Frontend: `http://localhost:13000`
- Backend: `http://localhost:15050`
- AI system: `http://localhost:18000`

The Docker frontend is built with:

```text
REACT_APP_API_BASE_URL=http://localhost:15050
```

Backend CORS is configured in Compose as:

```text
CORS_ORIGINS=http://localhost:13000,http://localhost:3000
```

## Main User Flow

1. Open `http://localhost:13000/`.
2. Select a portfolio.
3. Open the AI Analysis section and click `Run Analysis`.
4. Review the final real `analysis_trace`.

## Important API Docs

See [api.md](api.md) for the concise frontend/backend contract.

Common endpoints:

- `GET /health`
- `GET /api/portfolios`
- `GET /api/portfolios/{id}`
- `GET /api/portfolios/{id}/assets`
- `GET /api/portfolios/{id}/transactions`
- `POST /api/portfolios/{id}/analyze`
- `GET /api/symbols`
- `GET /api/sentiment?symbols=AAPL,MSFT`

## Azure Backend CI/CD

Workflow:

```text
.github/workflows/deploy-backend.yml
```

It builds `backend/Dockerfile` for `linux/amd64`, tags the image with `${{ github.sha }}`, pushes to:

```text
finguardacr.azurecr.io/finguard-backend:${{ github.sha }}
```

and updates Azure Container App:

```text
finguard-backend
```

Required GitHub secrets:

- `AZURE_CREDENTIALS`
- `AZURE_RESOURCE_GROUP`

## Current Gaps

- Some frontend flows still fall back to direct JSON responses because backend SSE endpoints are not implemented yet.
- Agent trace is real after completion, but not streamed live yet.
- Cases still rely on pasted bearer tokens instead of a full auth session UX.
- SQLite is suitable for demo, but cloud persistence needs hardening.
- CI/CD currently deploys backend only.

## Related Docs

- [PRD.md](PRD.md)
- [api.md](api.md)
- [FINGUARD_COMPREHENSIVE_GUIDE.md](FINGUARD_COMPREHENSIVE_GUIDE.md)
