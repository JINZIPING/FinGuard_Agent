# MLSecOps / LLMSecOps Pipeline Design

## Objectives

- make the demo build repeatable
- keep AI and backend changes testable in CI
- support deterministic smoke tests without live model dependencies

## Current CI Pipeline

The repository now includes `/.github/workflows/ci.yml` with three jobs:

- `frontend-build`
  - installs frontend dependencies
  - runs `npm ci`
  - runs `npm run build`
- `python-tests`
  - installs backend and AI dependencies
  - runs `pytest -q`
- `docker-smoke`
  - seeds deterministic demo data
  - writes `ai_system/.env` with `AI_RESPONSE_MODE=mock`
  - starts `docker compose`
  - checks health for frontend, backend, and AI system
  - exercises portfolio analysis, case list, and SAR export

## Deployment Workflows

Existing deployment workflows remain:

- `deploy-backend.yml`
- `deploy-ai-system.yml`

These publish container images and update Azure Container Apps.

## Model / AI Versioning

- live model selection is environment-driven:
  - `OPENAI_MODEL`
  - `OPENAI_REASONING_EFFORT`
- deterministic non-live mode is environment-driven:
  - `AI_RESPONSE_MODE=mock`
- persisted analysis records keep output artifacts for later review

## Automated Test Strategy

- unit and workflow tests
  - backend auth, cases, SAR, audit, and side effects
  - AI workflow routing and trace checks
- AI security tests
  - prompt-injection behavior in mock mode
  - unauthorized export checks
- smoke tests
  - seeded Docker stack health and main demo flows

## Secrets Handling

- API keys are injected through environment variables
- mock mode removes external-model dependency from CI
- no secrets are committed in repo artifacts

## Monitoring and Logging

- backend health endpoint
- AI health endpoint including `response_mode`
- Docker health checks for all three services
- audit trail for case/SAR-sensitive actions

## Rollback and Recovery

- deploy jobs publish immutable images tagged by commit SHA
- deterministic seed data and mock mode allow quick environment rebuilds
- rollback can be performed by redeploying the prior known-good image tag
