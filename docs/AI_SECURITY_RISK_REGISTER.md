# AI Security Risk Register

| Risk ID | Threat | Example Failure Mode | Current Controls | Residual Risk |
|---|---|---|---|---|
| AIR-01 | Prompt injection | Malicious portfolio or transaction text tries to override agent instructions | Mock-mode safeguard responses, backend-controlled orchestration, no direct tool execution from frontend | Medium |
| AIR-02 | Hallucinated recommendation | LLM invents unsupported risk rationale or recommendation details | Human review boundary, trace visibility, persisted outputs for audit, mock mode for test stability | Medium |
| AIR-03 | Secret exfiltration attempts | User asks model to reveal system prompt or credentials | No secrets exposed through frontend APIs, mock-mode refusal behavior, environment-based secrets | Low-Medium |
| AIR-04 | Data leakage across cases | Case or audit data becomes visible to another tenant/user | Tenant scoping in case/audit/SAR queries, optional enforced auth, role checks | Medium |
| AIR-05 | Privilege misuse | Analyst attempts supervisor-only actions | Role checks in case transition and audit verification flows | Low |
| AIR-06 | Poisoned knowledge content | Incorrect or malicious knowledge-base text affects analysis quality | Knowledge base is repo-managed, not end-user writable in the current demo | Medium |
| AIR-07 | Rate-limit / model outage | Live AI analysis fails during demo or investigation | `AI_RESPONSE_MODE=mock`, graceful rate-limit responses, CI smoke tests | Low |
| AIR-08 | Excessive input size | Oversized prompt-like values degrade service or destabilize output | API validation plus smoke/security tests ensuring non-500 handling | Medium |
| AIR-09 | Audit trail tampering | Investigation actions are modified after the fact | Hash-chained audit log verification endpoint | Low |
| AIR-10 | Unsafe autonomous closure | AI output directly closes or escalates a case without human confirmation | Backend keeps closure and SAR actions in explicit workflow endpoints | Low |

## Security Test Coverage

- prompt injection handling in mock mode
- unauthorized SAR access
- malformed transaction payload handling
- supervisor-only audit verification
- end-to-end suspicious transaction to case flow

## Recommended Future Controls

- request-size limits and WAF rules at deployment edge
- production prompt-safety middleware
- dependency and container image scanning in CI
- centralized monitoring/alerting for auth failures and abnormal API usage
