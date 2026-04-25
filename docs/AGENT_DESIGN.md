# FinGuard Agent Design

## Orchestration Model

FinGuard uses a LangGraph portfolio-review workflow with two routes:

- `quick`
  - `ingest_request -> run_quick_recommendation -> compile_quick_response`
- `full`
  - `ingest_request -> run_full_crew_one -> run_full_crew_two -> run_full_crew_three -> compile_full_response`

The workflow returns a final response plus an ordered `analysis_trace` containing node, crew, agent, status, duration, and body data.

## Agent Roles

### Crew 1: Risk Analysis

- Alert Intake Agent
  - Summarizes whether elevated ML risk signals justify human review
- Risk Assessment Agent
  - Scores portfolio and transaction risk using hybrid ML/rules plus LLM narrative
- Risk Detection Agent
  - Interprets suspicious transaction patterns and fraud indicators
- Compliance Agent
  - Adds policy and compliance framing for transaction behavior

### Crew 2: Portfolio Analysis

- Portfolio Analysis Agent
  - Evaluates concentration, diversification, and portfolio posture
- Market Intelligence Agent
  - Produces sentiment and recommendation outputs for symbols
- Customer Context Agent
  - Frames activity against account/portfolio context

### Crew 3: Summary and Escalation

- Explanation Agent
  - Produces analyst-facing summaries and human-readable reasoning
- Escalation Case Summary Agent
  - Recommends escalation or monitoring posture based on accumulated signals

## Reasoning and Planning Pattern

- Request ingestion prepares:
  - route selection
  - portfolio summary
  - transaction summary
  - ML pre-screen summary
- Each crew appends trace events rather than streaming mutable hidden state.
- Final compilers package output into a stable backend contract.

This pattern favors observable stage-by-stage reasoning over opaque chain-of-thought exposure.

## Tools and Shared Services

- ML risk engine
  - Used for deterministic transaction scoring
- Vector / knowledge-base lookups
  - Used by some backend workflows and supporting documentation paths
- Audit trail and persisted analysis store
  - Managed in backend, not directly by agents

## Memory and State

- Shared workflow state lives in `PortfolioAnalysisState`
- State fields include:
  - request metadata
  - portfolio/transaction payloads
  - ML summary
  - crew outputs
  - trace events
  - final response

This is short-lived execution state, not long-term conversational memory.

## Prompt and Fallback Strategy

- Live mode
  - `ai_system.app.llm.chat()` calls OpenAI Responses API
- Mock mode
  - `AI_RESPONSE_MODE=mock` returns deterministic canned outputs keyed off prompt intent
- Fallback behavior
  - Rate-limit handling sets `rate_limited=true`
  - Missing `langgraph` falls back to a sequential in-process graph shim
  - ML-unavailable paths degrade to LLM-only or safe fallback text

## Traceability

- Every portfolio review returns `analysis_trace`
- Backend persists portfolio analyses and transaction-risk analyses
- Case actions append `case_events`
- Audit-sensitive actions write tamper-evident hash-chained audit logs

## Coordination Protocol

- Frontend never calls internal agents directly
- Backend is the stable façade for user-facing workflows
- `ai_system` keeps debugging-friendly agent endpoints, but orchestration is intended to be driven by backend routes
