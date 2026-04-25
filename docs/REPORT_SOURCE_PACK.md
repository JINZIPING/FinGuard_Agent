# Report Source Pack

This file is the source-of-truth index for the group report, slides, and individual agent write-ups.

## Group Report Sections

- Executive summary
  - `README.md`
  - `PRD.md`
- System overview and architecture
  - `docs/SYSTEM_ARCHITECTURE.md`
- Agent roles and design
  - `docs/AGENT_DESIGN.md`
- Explainable and Responsible AI practices
  - `docs/RESPONSIBLE_AI_REPORT.md`
- AI security risk register
  - `docs/AI_SECURITY_RISK_REGISTER.md`
- MLSecOps / LLMSecOps pipeline
  - `docs/MLSECOPS_LLMSecOps_PIPELINE.md`
- Testing summary and demo walk-through
  - `docs/TESTING_AND_DEMO_RUNBOOK.md`

## Individual Report Inputs by Agent

- Risk Assessment Agent
  - `ai_system/app/agents/risk_assessment_agent.py`
- Portfolio Analysis Agent
  - `ai_system/app/agents/portfolio_analysis_agent.py`
- Market Intelligence Agent
  - `ai_system/app/agents/market_intelligence_agent.py`
- Explanation Agent
  - `ai_system/app/agents/explanation_agent.py`
- Compliance Agent
  - `ai_system/app/agents/compliance_agent.py`
- Customer Context Agent
  - `ai_system/app/agents/customer_context_agent.py`
- Alert Intake Agent
  - `ai_system/app/agents/alert_intake_agent.py`
- Escalation Case Summary Agent
  - `ai_system/app/agents/escalation_case_summary_agent.py`

## Demo / Verification Inputs

- deterministic seed workflow
  - `scripts/seed_demo_data.py`
- automated tests
  - `tests/`
- CI definition
  - `.github/workflows/ci.yml`
- API contract
  - `api.md`
