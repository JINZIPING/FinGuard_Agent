# FinGuard Comprehensive Guide

Last updated: 2026-04-26

## 1. Product Positioning

FinGuard is an explainable investigation workspace for financial fraud and portfolio risk review. The system is optimized for:

- visible multi-agent orchestration
- traceable analysis outputs
- human-reviewed case workflows
- assessment-ready architecture, security, and operational artifacts

It is not designed to take fully autonomous enforcement actions.

## 2. Service Architecture

```text
React Frontend
  -> FastAPI Backend
      -> SQLite persistence
      -> Audit / SAR / search / cases
      -> AI bridge
          -> FastAPI AI System
              -> LangGraph workflow
              -> 9 internal agents
              -> OpenAI live mode or deterministic mock mode
              -> ML/rules transaction scoring
```

## 3. Core User Journeys

### Journey A: Portfolio Analysis

1. Frontend loads portfolios from backend
2. User selects a portfolio
3. Backend gathers assets and transactions
4. Backend calls `ai_system`
5. LangGraph runs the portfolio review route
6. Backend returns `crew_output` and `analysis_trace`

### Journey B: Suspicious Activity Review

1. A suspicious transaction is recorded
2. Transaction risk scoring returns a high or critical score
3. Backend auto-creates:
   - alert
   - case
   - case event
   - persisted analysis
4. Analyst reviews the case and customer 360 context
5. Analyst exports SAR JSON or PDF if needed

## 4. Internal Agents

- Alert Intake
- Customer Context
- Risk Assessment
- Risk Detection
- Explanation
- Escalation Case Summary
- Portfolio Analysis
- Market Intelligence
- Compliance

These are code modules inside `ai_system`, not separate network services.

## 5. Explainability and Traceability

- portfolio analysis returns `analysis_trace`
- case workflows record `case_events`
- audit-sensitive actions write hash-chained audit log entries
- SAR exports include narrative, timeline, and saved AI analysis

## 6. Demo Reliability Features

### Deterministic Mock Mode

Use:

```env
AI_RESPONSE_MODE=mock
```

This removes the dependency on live model access and makes tests and demos reproducible.

### Seeded Demo Dataset

Run:

```bash
python scripts/seed_demo_data.py --reset
```

This creates:

- seeded demo users
- a demo portfolio
- demo assets
- normal and suspicious transactions
- an auto-opened case ready for the case/SAR storyline

## 7. Running Locally

1. Copy `ai_system/.env.example` to `ai_system/.env`
2. Optional: switch to mock mode for deterministic output
3. Seed the demo data
4. Run:

```bash
docker compose up --build
```

## 8. CI / Operational Workflow

`/.github/workflows/ci.yml` now covers:

- frontend build
- backend and AI tests
- Docker smoke tests with seeded data and mock mode

Deployment workflows remain in:

- `.github/workflows/deploy-backend.yml`
- `.github/workflows/deploy-ai-system.yml`

## 9. Assessment Documentation

Primary write-up files:

- `docs/SYSTEM_ARCHITECTURE.md`
- `docs/AGENT_DESIGN.md`
- `docs/RESPONSIBLE_AI_REPORT.md`
- `docs/AI_SECURITY_RISK_REGISTER.md`
- `docs/MLSECOPS_LLMSecOps_PIPELINE.md`
- `docs/TESTING_AND_DEMO_RUNBOOK.md`
- `docs/REPORT_SOURCE_PACK.md`

## 10. Current Boundaries

- live SSE trace streaming is still deferred
- SQLite remains a demo-friendly persistence layer
- fairness evaluation is documented, but not yet implemented as a full benchmark pipeline
- production edge security controls are outside this repo’s current scope
