# FinGuard PRD

Last updated: 2026-05-06

## 1. Product Definition

FinGuard is an AI-assisted investigation workspace for financial fraud and portfolio risk review. It helps analysts move from raw portfolio and transaction data to a traceable AI-supported risk assessment, with supporting workflows for market sentiment, case handling, audit review, and SAR-style reporting.

The product is not a fully autonomous fraud actioning system. It does not block transactions, freeze accounts, or replace analyst judgment. Its role is to organize evidence, run repeatable AI analysis, explain signals, and support human review.

## 2. Target Users

### Fraud Analyst

Needs to quickly understand whether portfolio or transaction activity is suspicious, what evidence supports the risk level, and whether a case should be escalated.

### Compliance or Risk Reviewer

Needs consistent explanations, audit history, policy-relevant signals, and exportable investigation records.

### Supervisor

Needs visibility into escalated cases, analyst actions, and whether decisions are supported by evidence.

### Demo Evaluator

Needs to see a clear multi-agent architecture, working AI orchestration, explainability, and deployability.

## 3. Product Positioning

FinGuard combines three product experiences:

- Portfolio risk workspace: select portfolios, inspect holdings and transactions, run analysis.
- Fraud investigation assistant: surface risk signals, explanations, and escalation recommendations.
- Compliance evidence layer: maintain audit logs, case history, and SAR exports.

The core differentiator is the visible multi-agent AI pipeline. Users can see which agents contributed to an assessment and what each stage produced.

## 4. Core User Journeys

### Journey 1: Run AI Portfolio Risk Analysis

1. User opens the AI Analysis page.
2. System loads available portfolios from the backend.
3. User selects a portfolio from a dropdown.
4. User clicks `Run Analysis`.
5. Frontend fetches portfolio, assets, and transactions.
6. Backend calls the AI system.
7. AI system runs LangGraph and internal agents.
8. Frontend shows progress while waiting.
9. Final response returns `analysis_trace`, `crew_output`, structured crew results, and top-level recommendation metadata.
10. User reviews agent outputs, trace metadata, and final recommendation.

Expected result:

- User can understand what happened, which agents ran, and why the recommendation was produced.

### Journey 2: Review Market Sentiment

1. User opens Sentiment page.
2. System loads supported stock symbols.
3. User selects one or more symbols.
4. Backend calls AI system market sentiment endpoint.
5. User reviews sentiment text and high-level market signal.

Expected result:

- User gets quick market context for selected symbols.

### Journey 3: Investigate a Suspicious Case

1. A suspicious transaction or portfolio pattern creates or suggests a case.
2. Analyst opens case list.
3. Analyst reviews case detail, timeline, notes, AI analysis, and customer context.
4. Analyst assigns the case, adds notes, or transitions state.
5. System records audit events.
6. If needed, user exports SAR JSON/PDF.

Expected result:

- Investigation decisions are traceable and exportable.

Current status:

- Backend supports this journey.
- Frontend cases page is still a placeholder.

### Journey 4: Deploy and Verify Cloud Backend

1. Developer merges code to `main`.
2. GitHub Actions builds backend Docker image for `linux/amd64`.
3. Workflow pushes image to ACR.
4. Workflow updates Azure Container App.
5. Developer verifies `/health`.

Expected result:

- Backend deployment is repeatable and tied to commit SHA.

## 5. Feature Requirements

### 5.1 Portfolio Selection

Purpose:

- Let users choose a portfolio without knowing internal IDs.

Requirements:

- Load portfolios from `GET /api/portfolios`.
- Show portfolio name, ID, and value.
- Disable analysis when no portfolio exists.
- Use selected portfolio for all analysis calls.

Current status:

- Implemented on AI Analysis page.

### 5.2 AI Analysis Trace

Purpose:

- Make AI decisions explainable and auditable.

Requirements:

- Run portfolio review through backend and AI system.
- Return final analysis text.
- Return `analysis_trace` with node, crew, agent, status, duration, output, structured summary, evidence references, and fallback metadata.
- Return structured `crew1_results`, `crew2_results`, and `crew3_results`.
- Return top-level action recommendation, priority tier, escalation recommendation, and evidence summary.
- Show agent trace in frontend.
- Preserve stable response shape for frontend compatibility.

Current status:

- Implemented as final-response trace.
- Not yet server-streamed in real time.

### 5.3 Internal Agent System

Purpose:

- Split analysis responsibilities into clear modules.

Agents:

- Alert Intake
- Customer Context
- Risk Assessment
- Risk Detection
- Explanation
- Escalation Summary
- Portfolio Analysis
- Market Intelligence
- Compliance

Requirements:

- Keep agent logic inside `ai_system`.
- Use LangGraph for production orchestration.
- Keep direct agent endpoints for debugging only.

### 5.4 Market Sentiment

Purpose:

- Provide market context for selected symbols.

Requirements:

- Load symbols from backend.
- Allow multiple symbol selection.
- Call backend sentiment endpoint.
- Show returned sentiment text.
- Gracefully handle AI errors.

Current status:

- Implemented.

### 5.5 Portfolio and Transaction Management

Purpose:

- Support portfolio data needed for risk analysis.

Requirements:

- Create/list portfolios.
- View portfolio details.
- Add/list assets.
- Add/list transactions.
- Trigger transaction risk scoring when transactions are created.

Current status:

- Backend implemented.
- Frontend portfolio page still uses local/static data.

### 5.6 Alerts

Purpose:

- Track analyst-facing price, risk, or fraud notifications.

Requirements:

- Create alert.
- List alerts by portfolio.
- Show active/triggered state.
- Support future risk-generated alerts.

Current status:

- Backend implemented.
- Frontend alert page still uses local/static data.

### 5.7 Case Management

Purpose:

- Provide human review workflow for suspicious activity.

Requirements:

- List cases with filters.
- View case detail and timeline.
- Create case.
- Assign case.
- Add notes.
- Transition case state.
- Run case analysis.
- View customer 360 context.

Current status:

- Backend implemented.
- Frontend page not implemented.

### 5.8 Audit and SAR

Purpose:

- Support traceability and compliance reporting.

Requirements:

- Record important case and SAR actions.
- Verify hash-chained audit log.
- Export SAR JSON.
- Export SAR PDF.

Current status:

- Backend implemented.
- Frontend workflow not implemented.

### 5.9 Auth and Roles

Purpose:

- Separate analyst, supervisor, and admin capabilities.

Requirements:

- Register/login/me endpoints.
- Bearer token support.
- Role checks for restricted actions.
- Production mode with enforced auth.

Current status:

- Backend implemented.
- Frontend login/register not implemented.

## 6. Current Gaps and Risks

- Many frontend pages are still static or local-state.
- Real AI trace is returned after completion, not streamed live.
- Frontend package lock is out of sync; Docker uses `npm install`.
- SQLite is acceptable for demo but not durable cloud persistence.
- CI/CD deploys backend only.
- Production auth requires explicit environment configuration.

## 7. Roadmap

### Phase 1: Demo Completeness

- Keep AI Analysis and Sentiment working end to end.
- Fix package lock and switch Dockerfile to `npm ci`.
- Keep docs and API contract aligned.

### Phase 2: Frontend-Backend Integration

- Wire Portfolio page to backend.
- Wire Alerts page to backend.
- Build Cases page.
- Add auth UI.

### Phase 3: Real-Time AI Experience

- Add SSE or polling for analysis status.
- Stream LangGraph node and agent events.
- Replace temporary frontend progress with real backend events.

### Phase 4: Production Hardening

- Add CI/CD for frontend and AI system.
- Add durable database/storage.
- Enforce auth and role configuration.
- Add integration tests.

## 8. Success Criteria

- User can select a portfolio and run AI analysis.
- User can see final agent trace and final recommendation.
- Sentiment analysis works from frontend to backend to AI system.
- Backend health and AI health pass in Docker.
- Backend deployment to Azure Container Apps is automated.
- Product gaps are clear and tracked.

## 9. Open Questions

- Should the next product priority be Cases or Portfolio management?
- Should real-time status use SSE or polling?
- Should frontend deploy as static hosting or container app?
- Should production persistence use PostgreSQL/Azure SQL or mounted SQLite storage?
