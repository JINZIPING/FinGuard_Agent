# FinGuard System Architecture

## Summary

FinGuard is a three-service analyst investigation system built around a React shell frontend, a FastAPI backend, and a FastAPI-based AI service. The system supports two main demo storylines:

1. Portfolio analysis with multi-agent `analysis_trace`
2. Suspicious transaction review leading to alert, case, and SAR export

The design goal is assessment-ready explainability and modularity rather than full production autonomy.

## Logical Architecture

```text
React Frontend
  -> Backend API (FastAPI)
      -> SQLite persistence
      -> Audit and SAR services
      -> Search / vector sync hooks
      -> AI service bridge over HTTP
          -> AI System (FastAPI)
              -> LangGraph workflow
              -> 9 internal agents
              -> OpenAI adapter or deterministic mock mode
              -> ML / rules risk adapter
```

## Physical / Deployment Architecture

- `frontend`
  - Built with React and served by Nginx in Docker
  - Consumes backend APIs through `REACT_APP_API_BASE_URL`
- `backend`
  - FastAPI application running on Uvicorn
  - Uses SQLite under `backend/data/backend.db`
  - Exposes REST APIs for portfolios, transactions, alerts, cases, audit, SAR, search, and health
- `ai_system`
  - FastAPI application running on Uvicorn
  - Hosts LangGraph orchestration and agent modules
  - Supports `AI_RESPONSE_MODE=live|mock`

Local orchestration is handled through `docker-compose.yml`, now with health checks for all three services.

## Data Flow

### Portfolio Analysis

1. User selects a portfolio in the frontend.
2. Frontend calls backend portfolio endpoints.
3. Backend normalizes portfolio and transaction data.
4. Backend calls `POST /orchestrate/portfolio-review` on `ai_system`.
5. `ai_system` runs the LangGraph route.
6. Final response returns `crew_output` and `analysis_trace`.
7. Backend persists the analysis and returns the stable frontend contract.

### Suspicious Transaction to Case

1. User records a transaction.
2. Backend calls `ai_system` transaction-risk scoring.
3. Backend stores the transaction.
4. If the risk score is `>= 55`, backend auto-creates:
   - alert
   - case
   - case event
   - persisted risk analysis
5. Case data becomes available through `/api/cases/*`.
6. SAR export is available through `/api/sar/{case_id}.json|pdf`.

## Technology Rationale

- FastAPI
  - Small, testable REST surface with strong request validation
- LangGraph
  - Makes the agent pipeline explicit and traceable
- SQLite
  - Sufficient for local/demo use with minimal setup
- Chroma-backed vector storage
  - Supports retrieval and analysis search
- scikit-learn hybrid risk engine
  - Provides deterministic ML/rule scoring independent of LLM availability
- Mock AI mode
  - Makes demos, CI, and security tests stable without external model calls

## Key Quality Attributes

- Explainability
  - `analysis_trace`, audit logs, and SAR exports expose decision context
- Modularity
  - Agent behavior stays in `ai_system`; business workflows stay in backend
- Maintainability
  - Stable API envelopes and isolated test fixtures reduce change risk
- Reliability
  - Docker health checks, CI smoke tests, and seeded demo data support repeatable demonstrations
