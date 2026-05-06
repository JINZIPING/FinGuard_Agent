# FinGuard Multi-Agent Logic And Strategy

Canonical report-alignment target: [docs/AGENT_ALIGNMENT_TARGET.md](docs/AGENT_ALIGNMENT_TARGET.md)

FinGuard uses a nine-agent analysis strategy. The system splits a portfolio review into three logical crews, then merges their findings into one analyst-facing result.

## Core Strategy

The workflow is designed around separation of concerns:

- Crew 1 identifies financial, fraud, and compliance risk.
- Crew 2 interprets portfolio quality, market context, and customer behavior.
- Crew 3 turns the findings into alert, explanation, and escalation decisions.

The strategy is not to let one large prompt decide everything. Each agent receives a narrower responsibility, produces focused output, and passes that output into the final synthesis.

## Logic Realization

### 1. Request Ingestion

The system receives:

- Portfolio metadata
- Asset positions
- Cash balance and total value
- Recent transactions

It normalizes this input into a shared graph state. That state is the working memory for all crews.

### 2. Crew Execution

The three crews run from the same portfolio and transaction context:

```text
Portfolio + Transactions
  -> Crew 1: Risk Analysis
  -> Crew 2: Portfolio Analysis
  -> Crew 3: Summary and Escalation
  -> Final Multi-Agent Analysis
```

Each crew writes its result into shared state:

- `crew1_output`
- `crew2_output`
- `crew3_output`

The final response combines those outputs into one review.

## Crew 1: Risk Analysis

### Risk Assessment Agent

Strategy:

- Quantify transaction and portfolio risk.
- Identify concentration, market, liquidity, and exposure concerns.
- Produce concrete mitigation suggestions.

Realization:

- Uses transaction and portfolio fields as structured evidence.
- Applies local scoring helpers for transaction risk signals.
- Uses LLM reasoning for higher-level portfolio risk interpretation.

Output:

- Portfolio risk summary
- Transaction risk reasoning
- Mitigation or hedging recommendations

### Risk Detection Agent

Strategy:

- Look for suspicious behavior rather than ordinary portfolio risk.
- Focus on fraud signals, abnormal activity, and transaction patterns.

Realization:

- Reuses transaction risk context from the risk module.
- Reviews recent transactions against fraud-oriented prompts.
- Produces analyst-facing fraud findings and action items.

Output:

- Fraud risk assessment
- Suspicious pattern explanation
- Suggested analyst follow-up

### Compliance Agent

Strategy:

- Check whether activity needs policy or regulatory review.
- Keep compliance findings separate from market and portfolio judgment.

Realization:

- Reviews transaction type and transaction volume.
- Flags unsupported or unusual transaction categories.
- Adds compliance notes into Crew 1 output.

Output:

- Compliance scan result
- Reporting or review notes

## Crew 2: Portfolio Analysis

### Portfolio Analyst

Strategy:

- Evaluate the portfolio as an investment structure.
- Separate allocation quality from fraud or compliance concerns.

Realization:

- Uses asset positions, prices, quantities, cash, and total value.
- Runs structured reasoning for allocation, diversification, performance, risk, and rebalancing.
- Stores intermediate reasoning steps before producing a final recommendation.

Output:

- Allocation analysis
- Diversification assessment
- Performance and risk notes
- Rebalancing suggestions

### Market Intelligence Agent

Strategy:

- Add symbol-level market context so portfolio recommendations are not based only on internal holdings.
- Keep market sentiment separate from risk/compliance logic.

Realization:

- Extracts symbols from assets and recent transactions.
- Summarizes which symbols were considered in the main workflow.
- Supports deeper LLM sentiment and recommendation analysis through dedicated market functions.

Output:

- Market context summary
- Optional symbol sentiment and investment recommendation

### Customer Context Agent

Strategy:

- Interpret the portfolio relative to customer behavior.
- Avoid treating all portfolios as identical when transaction patterns differ.

Realization:

- Uses portfolio name, asset count, and transaction count.
- Builds a behavior snapshot from the supplied data.
- Dedicated context functions can generate richer profile, history, needs, preference, and segment analysis when more customer data is provided.

Output:

- Customer behavior summary
- Context for later explanation and escalation decisions

## Crew 3: Summary And Escalation

### Alert Intake Agent

Strategy:

- Decide whether the current findings should become an alert.
- Convert raw findings into an analyst workflow decision.

Realization:

- Reviews previous risk context.
- Determines whether urgent review is needed.
- Produces a concise alert intake summary.

Output:

- Alert status
- Analyst review recommendation

### Explanation Agent

Strategy:

- Make multi-agent findings understandable.
- Convert technical risk, market, and compliance outputs into clear reasoning.

Realization:

- Receives Crew 1 and Crew 2 outputs.
- Uses LLM summarization to produce a coherent explanation.
- Can also explain individual alerts, recommendations, scores, portfolio performance, and compliance findings.

Output:

- Plain-language analysis summary
- Explanation of key reasons behind the recommendation

### Escalation Agent

Strategy:

- Decide whether the case should stay in monitoring or move to human review.
- Package the conclusion in operational language.

Realization:

- Uses risk and alert context.
- Creates an escalation path based on severity and repeated signals.
- Dedicated escalation functions can generate case summaries, escalation packages, resolution summaries, pattern reviews, and communication drafts.

Output:

- Escalation decision
- Human-review guidance
- Case-management summary

## Prompt Strategy

The system uses explicit role prompts instead of a single general prompt.

Prompt design principles:

- Give each agent a narrow role.
- Pass structured portfolio and transaction data into the prompt.
- Ask for operationally useful output, not generic financial commentary.
- Keep risk, market, compliance, customer, explanation, and escalation reasoning separate until final synthesis.

## RAG Strategy

RAG is used as supporting knowledge, not as the main orchestration mechanism.

Current strategy:

- Backend owns knowledge-base retrieval.
- Retrieved context can be passed into AI search and answer generation.
- The nine-agent portfolio review mainly uses live portfolio and transaction payloads.
- Domain documents support financial, risk, compliance, market, explanation, customer, and escalation knowledge when search context is needed.

## Tool Strategy

Current tool use is internal and deterministic where possible:

- Transaction risk helpers for structured risk signals
- Portfolio analysis functions for allocation review
- Fraud detection logic for suspicious activity checks
- Compliance snapshot logic for basic policy review
- Market symbol extraction for market context
- Customer snapshot logic for behavior context
- Explanation and escalation functions for final analyst output

External live market-data, brokerage, sanctions-screening, and database tools are not called directly inside the nine-agent workflow.
