# FinGuard

FinGuard is an AI-assisted fraud and portfolio risk investigation workspace built for explainable multi-agent demos. It combines a React shell frontend, a FastAPI backend, and a FastAPI AI service with LangGraph orchestration, hybrid ML/rule scoring, case management, audit logs, and SAR export.

```text
Frontend (React + HTML shell)
  -> Backend (FastAPI)
      -> SQLite / audit / cases / SAR / search
      -> AI bridge
          -> AI System (FastAPI + LangGraph)
              -> 9 internal agents
              -> OpenAI live mode or deterministic mock mode
              -> ML/rules risk engine
```

## What Works Today

- portfolio selection and AI analysis with final `analysis_trace`
- market sentiment and recommendation flows
- transaction risk scoring with auto-opened alerts and cases
- case management, customer 360, audit verification, and SAR JSON/PDF export
- deterministic demo seeding via `scripts/seed_demo_data.py`
- deterministic `AI_RESPONSE_MODE=mock` for tests, demos, and Docker smoke checks
- automated pytest suite and CI workflow
- Docker health checks for frontend, backend, and AI system

## Assessment Artifact Pack

- [System Architecture](docs/SYSTEM_ARCHITECTURE.md)
- [Agent Design](docs/AGENT_DESIGN.md)
- [Responsible AI Report](docs/RESPONSIBLE_AI_REPORT.md)
- [AI Security Risk Register](docs/AI_SECURITY_RISK_REGISTER.md)
- [MLSecOps / LLMSecOps Pipeline](docs/MLSECOPS_LLMSecOps_PIPELINE.md)
- [Testing and Demo Runbook](docs/TESTING_AND_DEMO_RUNBOOK.md)
- [Report Source Pack](docs/REPORT_SOURCE_PACK.md)

## Quick Start

1. Copy `ai_system/.env.example` to `ai_system/.env`
2. For a deterministic local demo, set:

```env
AI_RESPONSE_MODE=mock
```

3. Seed the demo dataset:

```bash
python scripts/seed_demo_data.py --reset
```

4. Start the stack:

```bash
docker compose up --build
```

URLs:

- Frontend: `http://localhost:13000`
- Backend: `http://localhost:15050`
- AI system: `http://localhost:18000`

## Main Demo Storylines

### 1. Portfolio Analysis with Explainability

1. Open the frontend
2. Go to `AI Analysis`
3. Run analysis on the seeded demo portfolio
4. Review:
   - final narrative
   - `analysis_trace`
   - multi-agent stage outputs

### 2. Suspicious Transaction to SAR

1. Open `Cases`
2. Load the seeded suspicious case
3. Review customer 360, timeline, and AI analysis actions
4. Export SAR JSON or PDF

## Environment Notes

### Backend

- `BACKEND_DB_PATH=./data/backend.db`
- `AI_SYSTEM_URL=http://ai_system:8000` in Docker
- `AUTH_ENFORCED=false` for demo mode
- `JWT_SECRET=<set in controlled environments>`

### AI System

- `OPENAI_API_KEY=<required for live mode>`
- `OPENAI_MODEL=gpt-5.4-mini`
- `OPENAI_REASONING_EFFORT=medium`
- `AI_RESPONSE_MODE=live|mock`

## Testing

Run the automated test suite:

```bash
pytest -q
```

CI also runs:

- frontend build checks
- backend + AI tests
- Docker smoke checks with seeded demo data

## API Contract

See [api.md](api.md) for the current backend/frontend contract and operational notes.
