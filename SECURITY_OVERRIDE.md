# Security Override Playbook

This document defines when and how to use `security_override=true` in CI workflows.

## Scope

Applies to:

- `.github/workflows/backend-tests.yml`
- `.github/workflows/ai-system-tests.yml`
- `.github/workflows/integration-tests.yml`

These workflows require an `override_reason` when `security_override=true`.

## When Override Is Allowed

Use override only for time-sensitive situations such as:

- Production incident mitigation
- Critical customer-impacting fix
- Emergency rollback/forward where patching vulnerable dependency immediately is not feasible

Do not use override for routine feature delivery.

## Required Override Reason Format

Use this exact structure in `override_reason`:

`INC:<ticket-or-incident-id>; OWNER:<name>; EXPIRES:<YYYY-MM-DD>; MITIGATION:<short-control>; PLAN:<short-remediation-plan>`

Example:

`INC:SEV2-1842; OWNER:Raja; EXPIRES:2026-05-01; MITIGATION:WAF rule + feature flag; PLAN:Pin patched dependency and remove override in next release`

## Approval Expectations

- Obtain approval from tech lead or security owner before triggering override.
- Keep override window short and bounded by `EXPIRES`.
- Open or link a tracking ticket for remediation.

## After-Action Requirements

Within 24 hours (or next business day):

- Remove override usage
- Patch/upgrade affected dependency
- Re-run CI without override
- Post outcome in incident/ticket thread

## Audit Trail

Workflows log override usage in `GITHUB_STEP_SUMMARY` with:

- Workflow name
- Actor
- Git ref
- Provided reason

Treat this as a permanent compliance record.
