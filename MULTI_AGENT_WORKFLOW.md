# FinGuard Multi-Agent AI Workflow

This document describes the current FinGuard AI-system workflow as implemented in `ai_system`.

## Runtime Architecture

```text
Frontend
  -> Backend FastAPI
       -> AI System FastAPI
            -> LangGraph portfolio-review workflow
            -> Internal agent modules
            -> OpenAI adapter
            -> Optional ML/rule risk engine
            -> Optional vector/RAG context through backend search
```

The production AI entrypoint is:

```text
POST /orchestrate/portfolio-review
```

Backend calls this endpoint for portfolio AI analysis. Direct `/agents/*/invoke` endpoints exist for debugging and compatibility, but the main production workflow should go through LangGraph.

## Main LangGraph Workflow

File:

```text
ai_system/langgraph/workflows/portfolio_review.py
```

Workflow:

```text
ingest_request
  -> choose_analysis_route
      -> quick:
          run_quick_recommendation
          -> compile_quick_response
      -> full:
          run_full_crew_one
          -> run_full_crew_two
          -> run_full_crew_three
          -> compile_full_response
```

State object:

```text
PortfolioAnalysisState
```

Important state fields:

- `portfolio`: portfolio snapshot from backend
- `transactions`: recent transactions from backend
- `route`: `quick` or `full`
- `ml_summary`: rule/ML pre-screening summary
- `crew1_output`, `crew2_output`, `crew3_output`: staged agent outputs
- `analysis_trace`: frontend-friendly execution trace
- `rate_limited`: whether model quota/rate limits were hit
- `response`: final API response

## Quick Analysis Path

The quick path is used when `mode=quick`.

```text
ingest_request
  -> run_quick_recommendation
  -> compile_quick_response
```

It uses:

- ML/rule transaction pre-screening
- Risk Assessment Agent prompt
- One OpenAI call for a short recommendation
- LangSmith trace events for the graph and model call

Purpose:

- Fast analyst feedback
- Lower token usage
- Suitable for dashboard interaction and quick checks

## Full Analysis Path

The full path is used when `mode=full`.

```text
Crew 1: Risk Analysis
  - Risk Assessment Agent
  - Risk Detection Agent
  - Compliance Agent

Crew 2: Portfolio Analysis
  - Portfolio Analyst
  - Market Intelligence Agent
  - Customer Context Agent

Crew 3: Summary and Escalation
  - Alert Intake Agent
  - Explanation Agent
  - Escalation Agent
```

The crews run sequentially in LangGraph. Each crew writes output into graph state, and the final response merges all crew results with the ML pre-screening summary.

## Agent Realization

### Risk Assessment Agent

Files:

```text
ai_system/app/agents/risk_assessment_agent.py
ai_system/app/ml.py
```

Responsibilities:

- Score transaction risk
- Assess portfolio risk
- Calculate market, concentration, liquidity, counterparty, currency, and interest-rate risk
- Recommend hedging and mitigation actions

Implementation:

- Uses a hybrid risk engine when model artifacts are available.
- Risk engine combines:
  - deterministic rules
  - trained ML models when present
  - IsolationForest-style anomaly scoring when present
- If ML is missing or a transaction needs deeper review, it falls back to LLM prompts.
- Produces `risk_score`, `risk_label`, `flags`, `hard_block`, and rule/ML details.

Prompt use:

- Deep-dive explanation for borderline/high-risk transactions
- Portfolio market exposure analysis
- Concentration risk analysis
- Comprehensive risk assessment
- Hedging strategy generation

Tool/data use:

- Internal ML/rule engine via `get_risk_engine()`
- No external market-data API call in the current implementation

### Risk Detection Agent

File:

```text
ai_system/app/agents/risk_assessment_agent.py
```

Responsibilities:

- Detect fraud and suspicious transaction behavior
- Review transaction history for AML/fraud signals
- Identify high-risk transactions from ML pre-scores

Implementation:

- Reuses the risk module.
- Uses ML pre-screening as baseline evidence.
- Runs LLM prompts for:
  - high-risk transaction analysis
  - portfolio-level fraud risk
  - comprehensive fraud assessment

Output:

- Fraud risk assessment
- Key drivers
- Transaction alerts
- SAR recommendation if warranted
- Immediate action items

### Compliance Agent

File:

```text
ai_system/app/agents/compliance_agent.py
```

Responsibilities:

- Review transactions for policy and regulatory concerns
- Generate tax-oriented transaction summaries
- Flag simplified compliance issues

Implementation:

- Quick mode uses rule-like checks:
  - unsupported transaction types
  - high transaction volume
- Full/debug mode uses LLM prompts for:
  - PDT concerns
  - wash-sale concerns
  - insider-trading concerns
  - reporting requirements
  - tax implications
  - AML flags

Tool/data use:

- No external compliance database integration yet.
- Uses transaction data supplied by backend.

### Portfolio Analyst

File:

```text
ai_system/app/agents/portfolio_analysis_agent.py
```

Responsibilities:

- Analyze asset allocation
- Evaluate diversification
- Assess portfolio performance and risk profile
- Generate rebalancing suggestions

Implementation:

- Full analysis uses multi-step prompting:
  1. asset allocation analysis
  2. diversification assessment
  3. performance and risk analysis
  4. final recommendation synthesis

Prompt use:

- Each step sends portfolio JSON to the OpenAI adapter.
- Step outputs are stored as `thinking_steps` and surfaced in the frontend trace.

Tool/data use:

- Uses portfolio snapshot only.
- No live benchmark/price API in the current agent.

### Market Intelligence Agent

File:

```text
ai_system/app/agents/market_intelligence_agent.py
```

Responsibilities:

- Analyze market sentiment
- Generate investment recommendations

Implementation:

- Uses prompt-based OpenAI calls.
- Optional `news_context` can be passed into sentiment analysis.
- Returns `rate_limited=true` if OpenAI quota/rate limit is hit.

Prompt use:

- Sentiment score from `-1` to `1`
- Key drivers
- Confidence level
- Short-term outlook
- Long-term outlook
- Buy/Hold/Sell recommendation
- Position sizing and catalysts

Tool/data use:

- No live news API is called by this module.
- Backend can store market outputs into vector search after analysis.

### Customer Context Agent

File:

```text
ai_system/app/agents/customer_context_agent.py
```

Responsibilities:

- Build customer profiles
- Summarize customer history
- Assess customer needs
- Extract preferences
- Classify customer segment

Implementation:

- Prompt-based agent.
- Currently uses supplied profile, history, and interaction payloads.

Tool/data use:

- No direct customer database query inside AI system.
- Backend is responsible for passing relevant customer context.

### Alert Intake Agent

File:

```text
ai_system/app/agents/alert_intake_agent.py
```

Responsibilities:

- Categorize incoming alerts
- Prioritize alert batches
- Validate alert integrity
- Route alerts toward downstream review

Implementation:

- Uses the risk engine for transaction/payment/transfer/withdrawal alerts when available.
- Adds ML score, label, method, hard-block status, and flags into the prompt context.
- Uses LLM prompts for categorization and routing.

Output:

- Alert type
- Priority
- Affected areas
- Recommended next action
- Optional `ml_risk` details

### Explanation Agent

File:

```text
ai_system/app/agents/explanation_agent.py
```

Responsibilities:

- Explain alerts
- Explain recommendations
- Explain transaction risk scores
- Explain portfolio performance
- Explain compliance findings
- Summarize multi-agent analysis

Implementation:

- Prompt-based agent.
- Has fallback logic for transaction risk explanations if the LLM call fails.
- Used in full workflow Crew 3 to summarize prior crew outputs.

Prompt use:

- Adapts tone and detail to the target audience.
- Produces analyst/customer-readable narratives.

### Escalation Agent

File:

```text
ai_system/app/agents/escalation_case_summary_agent.py
```

Responsibilities:

- Evaluate whether incidents require escalation
- Generate case summaries
- Prepare escalation packages
- Summarize resolutions
- Identify escalation patterns
- Draft escalation communication

Implementation:

- Prompt-based agent.
- Uses case, interaction, decision, severity, and customer payloads supplied by backend.

Tool/data use:

- No direct case database access inside AI system.
- Backend owns case persistence and SAR export.

## RAG and Knowledge Search

RAG is currently implemented across backend search plus AI-system generation.

Backend search routes:

```text
POST /api/search/analyses
POST /api/search/risks
POST /api/search/market
```

Backend behavior:

1. Calls AI guardrail:

   ```text
   POST /guardrail/check-query
   ```

2. Retrieves context from vector store if available:

   ```text
   vector_store.search_portfolio(...)
   vector_store.search_risk(...)
   vector_store.search_market(...)
   ```

3. Falls back to SQL search if vector search has no result.

4. Sends retrieved context to AI system:

   ```text
   POST /search/knowledge
   ```

AI-system behavior:

- Builds a prompt with up to five retrieved context documents.
- If context exists, asks the model to answer based on those documents.
- If context is missing, falls back to general financial knowledge.

Current RAG boundary:

- Retrieval is owned by backend.
- Answer generation is owned by AI system.
- The AI system does not directly query Chroma/vector storage.

## Prompting Strategy

The system uses explicit task prompts rather than autonomous tool-calling agents.

Prompt patterns:

- Role framing: “You are a financial fraud detection expert…”
- Structured instructions: numbered expected outputs
- Domain-specific context: portfolio JSON, transactions, ML summaries, customer details
- Synthesis prompts: combine previous step outputs into recommendations

The most complex prompt chains are:

- Portfolio Analyst: allocation -> diversification -> performance/risk -> recommendations
- Risk Assessment: market exposure -> concentration risk -> comprehensive risk
- Risk Detection: high-risk transaction review -> portfolio fraud review -> final fraud assessment

## Tool Use and External Integrations

Current tool-like capabilities:

- OpenAI model calls through `ai_system/app/llm.py`
- LangGraph orchestration
- LangSmith tracing
- ML/rule risk scoring through `get_risk_engine()`
- Backend vector search / RAG context
- Backend persistence in PostgreSQL/SQLite-compatible database layer
- Backend case, audit, SAR, search, and analysis storage

Not currently implemented:

- Live market-data API inside AI system
- Direct agent access to database
- Autonomous function calling/tool calling by the LLM
- Separate agent containers
- Parallel LangGraph crew execution

## OpenAI Adapter

File:

```text
ai_system/app/llm.py
```

Responsibilities:

- Centralize OpenAI calls
- Apply LangSmith tracing
- Handle retry/backoff
- Detect rate limits
- Fail over from `OPENAI_API_KEY` to `OPENAI_API_KEY_BACKUP` on rate limit

Environment variables:

```text
OPENAI_API_KEY
OPENAI_API_KEY_BACKUP
OPENAI_MODEL
OPENAI_REASONING_EFFORT
```

Failover behavior:

- Primary key is used first.
- Backup key is tried only when the primary key gets a rate-limit error.
- Non-rate-limit failures, such as bad key or bad model name, fail normally.

## LangSmith Monitoring

LangSmith is enabled through Docker/ACA environment variables:

```text
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=finguard
LANGSMITH_API_KEY=<secret>
```

Traced units:

- `portfolio_review_orchestration`
- LangGraph nodes:
  - `langgraph_ingest_request`
  - `langgraph_quick_recommendation`
  - `langgraph_crew_1_risk_analysis`
  - `langgraph_crew_2_portfolio_analysis`
  - `langgraph_crew_3_summary_escalation`
  - `langgraph_compile_quick_response`
  - `langgraph_compile_full_response`
- OpenAI calls:
  - `openai_chat`
  - provider-level OpenAI model run

This lets developers and reviewers inspect:

- input payload
- selected route
- executed nodes
- prompt/model calls
- latency
- token usage
- estimated cost
- output
- failures or rate limits

## Frontend Progress Trace

The AI system also emits `analysis_trace` for frontend display.

Trace event types:

- `terminal`
- `divider`
- `agent`
- `thinking`

This is separate from LangSmith. LangSmith is for developer monitoring. `analysis_trace` is for user-facing workflow visualization in the FinGuard UI.

## Current Limitations

- Full workflow crews are sequential, not parallel.
- Market intelligence is prompt-based and does not fetch live news/prices itself.
- Customer context and escalation agents depend on context passed by backend.
- RAG retrieval is backend-owned; AI system only receives retrieved documents.
- ML risk model files may be absent; when absent, risk scoring falls back to rules/LLM behavior.
- Some direct agent routes are compatibility/debug surfaces rather than the preferred production path.

