# Testing Summary and Demo Runbook

## Automated Testing Summary

Run locally:

```bash
pytest -q
```

Covered scenarios:

- AI-system health and mock mode visibility
- quick and full LangGraph route behavior
- `analysis_trace` presence and agent coverage
- demo seed generation
- portfolio analysis round-trip through backend
- suspicious transaction -> case -> SAR flow
- auth-required case and SAR routes
- supervisor-only audit verification
- prompt-injection handling in mock mode
- malformed payload handling

## Demo Preparation

1. Create `ai_system/.env` from `ai_system/.env.example`
2. For deterministic demos, set:

```env
AI_RESPONSE_MODE=mock
```

3. Seed the demo database:

```bash
python scripts/seed_demo_data.py --reset
```

4. Start the stack:

```bash
docker compose up --build
```

## Demo Storyline 1: Portfolio Analysis

1. Open the frontend at `http://localhost:13000`
2. Go to `AI Analysis`
3. Use the seeded demo portfolio
4. Run full analysis
5. Show:
   - final narrative
   - `analysis_trace`
   - nine-agent orchestration
   - explainability through visible stages

## Demo Storyline 2: Compliance / Case Workflow

1. Open `Cases`
2. Load the seeded suspicious case
3. Show:
   - case metadata
   - timeline
   - customer 360
   - case analysis actions
4. Export SAR JSON or PDF
5. Explain:
   - risk flags
   - human review boundary
   - auditability and reportability

## Suggested Talking Points for the Assessment

- Responsible AI:
  - advisory-only design, explainability trace, human oversight
- AI security:
  - prompt-injection testing, auth controls, audit chain
- Agentic AI:
  - specialized roles coordinated through LangGraph
- Integration and deployment:
  - Docker stack, CI, health checks, seeded demo, mock mode
