# Explainable and Responsible AI Report

## Scope

This report covers the current FinGuard demo implementation across development, testing, and deployment preparation.

## Human Oversight Boundary

- FinGuard is decision-support software
- It does not freeze assets, block accounts, or file SARs automatically
- Analysts and supervisors remain accountable for:
  - case transitions
  - escalation decisions
  - SAR export and submission

## Explainability Approach

- Portfolio analysis returns `analysis_trace` so users can inspect which agent stages ran
- Transaction review stores flags, risk scores, and analysis metadata
- Case workflows keep event timelines
- Audit-sensitive actions are hash-chained for post-hoc review
- SAR exports carry narrative, timeline, and attached AI analysis

## Fairness and Bias Considerations

The current system is a demo, so fairness work is framed as controlled risk reduction:

- protected-class attributes are not first-class decision inputs in the exposed API
- seeded demo scenarios are synthetic rather than human-subject data
- the ML/rule engine exposes contributing flags and labels for review
- final case closure remains a human decision

Known limits:

- no formal fairness benchmark dataset is included
- no group fairness metrics are currently computed
- geographic and sanctions-related signals may correlate with sensitive contexts and require human interpretation

## Accountability and Governance

- role-based access controls separate analyst, supervisor, and admin capabilities
- `AUTH_ENFORCED` can be turned on for controlled environments
- audit logs record user, action, resource, and chained hashes
- case transitions enforce explicit legal state paths
- AI outputs are advisory and retained alongside human workflow events

## Safety Controls

- deterministic mock mode supports offline validation and repeatable security testing
- AI-specific prompt-injection checks are tested in mock mode
- malformed payload handling is covered in API tests
- sensitive report export endpoints can be protected by auth and roles

## Limitations

- no formal fairness dashboard
- no production-grade model monitoring service
- no live red-team gateway in front of model prompts
- SQLite is demo-friendly, not enterprise-grade persistence

## Next Responsible-AI Improvements

- add fairness evaluation datasets and metrics for transaction scoring
- add policy-backed prompt safety middleware for live mode
- add explicit human override annotations in case workflows
- log model/version metadata more granularly in persisted analyses
