# FinGuard Agent Alignment Target

Last updated: 2026-05-06

## Purpose

This document is the canonical implementation target for aligning the repo with the project report `Group_Project_Report_Team36.docx`.

It exists because the repo currently contains a mix of:

- report-era intended behavior
- currently implemented behavior
- older simplifications and placeholders

When these differ, use this document as the source of truth for refactoring decisions until the code is fully aligned.

## Source Priority

For agentic workflow behavior, use the following priority order:

1. The project report sections describing system overview, agent roles, workflow, explainability, and testing expectations
2. This alignment target document
3. Existing code and internal markdown docs

If existing code or internal docs conflict with this document, treat them as implementation debt unless there is a strong technical reason to revise this target explicitly.

## Report Contradictions Resolved

The report mixes a few ideas that need to be normalized before implementation work:

### 1. Sequential crews vs parallel crews

The report mentions both sequential crew execution and a later optimization involving parallel execution.

Canonical target:

- The logical workflow is sequential across crews.
- Crew 1 output must be available before Crew 2 synthesis consumers rely on it.
- Crew 2 output must be available before Crew 3 synthesis consumers rely on it.
- Internal optimizations are acceptable only if they preserve the same dependency semantics and final state shape.

Implementation rule:

- Do not let Crew 3 start from partial or placeholder Crew 1 or Crew 2 data.

### 2. Customer Context location

The report places Customer Context in Crew 2, but also says it provides behavioral context to Risk Assessment and Compliance.

Canonical target:

- Customer Context remains a Crew 2-owned agent from a responsibility standpoint.
- A request-scoped customer context artifact must be available early enough for Risk Assessment and Compliance to consume where needed.

Implementation rule:

- This may be realized by a pre-crew customer context preparation step, or by splitting the agent into:
  - an early context extraction handoff artifact
  - a Crew 2 interpretation/synthesis step
- The external product story still presents Customer Context as part of Crew 2.

### 3. Alert Intake role

The report describes Alert Intake as a real synthesis agent, not a placeholder router.

Canonical target:

- Alert Intake must consume accumulated signals from Crews 1 and 2.
- It must not rely only on a synthetic mini-alert derived from a single score and a compliance count.

### 4. Explanation role

The report describes Explanation as an explainability layer grounded in structured intermediate signals.

Canonical target:

- Explanation must consume structured upstream outputs and cite concrete evidence.
- It must not depend only on flattened prose summaries when structured data is available.

### 5. Escalation role

The report describes Escalation as the final case synthesis layer with action recommendation and evidence portfolio.

Canonical target:

- Escalation must assemble a case dossier from raw upstream artifacts, not only from reduced strings.

## Canonical Full-Path Workflow

The intended full analysis flow is:

```text
ingest_request
  -> create request-scoped shared state
  -> generate ML pre-screening summary
  -> establish request-scoped customer context seed if needed
  -> Crew 1: Risk and Compliance
  -> Crew 2: Portfolio Analysis
  -> Crew 3: Summary and Escalation
  -> compile_full_response
```

### Crew 1: Risk and Compliance

Agents:

- Risk Assessment Agent
- Risk Detection Agent
- Compliance Agent

Required behavior:

- Use portfolio and transaction context as primary evidence.
- Use ML/rules outputs where available.
- Produce structured outputs, not just narrative text.
- Persist raw structured artifacts into shared state for downstream consumption.

Required Crew 1 state artifacts:

- transaction-level ML/risk outputs
- portfolio-level risk assessment output
- fraud-pattern / anomaly output
- compliance output with rule hits, severity, and actions

### Crew 2: Portfolio Analysis

Agents:

- Portfolio Analysis Agent
- Market Intelligence Agent
- Customer Context Agent

Required behavior:

- Portfolio Analysis evaluates allocation, diversification, liquidity, and practical portfolio actions.
- Market Intelligence provides symbol-level market context with explicit note when live data is absent.
- Customer Context produces behavioral/profile interpretation and consistency signals.

Required Crew 2 state artifacts:

- portfolio analysis structured output
- market intelligence structured output
- customer context structured output
- request-scoped behavioral consistency indicators

### Crew 3: Summary and Escalation

Agents:

- Alert Intake Agent
- Explanation Agent
- Escalation Agent

Required behavior:

- Alert Intake converts multi-agent findings into routing and priority signals.
- Explanation converts technical findings into auditable, plain-language reasoning.
- Escalation produces the final case summary, evidence portfolio, and action recommendation.

Required Crew 3 state artifacts:

- alert intake routing output
- explanation output grounded in upstream evidence
- escalation evaluation output
- escalation case summary output

## Canonical Inter-Agent Contracts

Every agent must produce a machine-consumable payload in addition to human-readable text.

Minimum contract shape:

- `agent`
- `timestamp`
- `structured_output`

Minimum `structured_output` shape:

- `summary`
- `severity`
- `confidence`
- `key_factors`
- `recommended_actions`
- `follow_up`
- `raw_text`

### Additional required contract fields by agent family

Risk and Compliance:

- explicit scores or labels where available
- rule hits or flags where available
- method/basis metadata where available

Customer Context:

- behavior profile summary
- consistency score
- consistency label
- behavioral flags

Alert Intake:

- escalation recommendation
- urgency level
- priority tier
- routing rationale

Explanation:

- explicit evidence references back to upstream agents
- cited signals or contributing factors

Escalation:

- action recommendation: `Decline`, `Escalate`, or `Report`
- priority tier
- evidence portfolio
- handoff readiness / case summary fields

## Canonical Shared State Expectations

The shared LangGraph state must preserve both human-readable crew summaries and raw structured artifacts.

Required top-level state areas:

- request metadata
- normalized portfolio and transaction payloads
- ML pre-screening summary
- Crew 1 results
- Crew 2 results
- Crew 3 results
- analysis trace
- final response

Required rule:

- Later crews should consume `crew*_results` structured artifacts first.
- `crew*_output` is a presentation layer, not the canonical machine handoff.

## Canonical Explainability Rules

The report treats explainability as a first-class workflow concern.

Implementation rules:

- Preserve per-agent outputs in shared state.
- Preserve per-agent execution trace in `analysis_trace`.
- Explanation and Escalation must cite upstream evidence rather than invent new unsupported reasoning.
- Risk thresholds and routing rules should remain explicit and auditable, not hidden in prompts.

## Canonical analysis_trace Expectations

The analyst-facing trace should support per-agent visibility.

Each agent execution event should include at minimum:

- `sequence`
- `type`
- `node`
- `crew`
- `name`
- `status`
- `duration_ms`
- `body`

Optional but preferred where available:

- thinking events
- `contract_version`
- `agent`
- structured output snapshots
- `severity`
- `confidence`
- evidence references
- rate-limit or fallback indicators
- `data_basis` metadata when an agent relied on non-live or partial context

## Canonical Response Payload Expectations

The final full-path response should include:

- `timestamp`
- `portfolio_id`
- `crew_output`
- `agents_used`
- `crews_run`
- `rate_limited`
- `langgraph_route`
- `analysis_trace`
- `crew1_results`
- `crew2_results`
- `crew3_results`
- `response_contract_version`
- `final_action_recommendation`
- `final_priority_tier`
- `final_escalation_recommendation`
- `evidence_summary`
- `evidence_portfolio`

## Current Known Gaps Against This Target

The previously identified report-alignment gaps in the LangGraph full-path workflow are now addressed in the current implementation.

### Aligned In The Current Implementation

1. Customer Context creates a request-scoped context seed and influences Crew 1 consumers.
2. Alert Intake consumes accumulated upstream findings rather than only a reduced synthesized mini-alert.
3. Explanation receives structured upstream evidence rather than relying only on flattened crew summaries.
4. Escalation receives a richer structured dossier assembled from upstream artifacts.
5. Shared LangGraph crew handoffs use explicit typed contracts plus normalization helpers.
6. `analysis_trace` now carries richer auditability fields, including structured summaries, evidence references, and fallback markers.
7. The final response payload now returns structured crew result blocks, top-level action metadata, and evidence summaries alongside `crew_output`.

### Remaining Maintenance Work

The remaining work is primarily operational rather than report-alignment debt:

1. Keep downstream docs and UI consumers synchronized as the response contract evolves.
2. If needed, extend runtime validation beyond the core LangGraph full-path so debugging endpoints and future workflows enforce the same contract rigor.

## Acceptance Criteria For Full Alignment

The implementation can be considered aligned with the report when all of the following are true:

1. Each of the nine agents is invoked in the full path with its intended responsibility.
2. Each downstream consumer reads structured upstream artifacts rather than only flattened prose.
3. Customer context is available wherever the report says it informs risk/compliance reasoning.
4. Alert Intake routing uses combined Crew 1 and Crew 2 findings.
5. Explanation cites concrete upstream evidence.
6. Escalation produces a final dossier with action recommendation and evidence portfolio.
7. `analysis_trace` exposes per-agent execution visibility consistent with the report.
8. Tests cover cross-agent handoffs, not just isolated agent outputs.
9. The final response payload and `analysis_trace` expose the level of auditability and structured transparency described in the report.
