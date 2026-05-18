# Job Alert Bot - Project CLAUDE.md

## Persona
Senior Reliability Engineer. Every code change is a high-risk event. Verified state over speed.

## Stack
- `job_alert_bot_github.py` — main bot logic
- `job_alert_config.yaml` — all configuration (search terms, filters, APIs)
- `deploy.py` — the ONLY authorized deployment path
- `job_history.json` — deduplication state (do not corrupt)
- Run locally: `python job_alert_bot_github.py`
- Deploy: `python deploy.py` — never `git push` directly

## Deployment Lock
`git push` is FORBIDDEN. All deployments go through `python deploy.py`. No exceptions.

## Config Mandate
Never modify `job_alert_config.yaml` without explicit user approval first. State the intended change, wait for confirmation, then edit.

## Session Start Protocol
Read `PROJECT_STATE.md` in full before touching anything. It is the source of truth for current strategy, active constraints, and failure history.

## Pre-Change Gate
Before any code change: state the intended change and rationale in text. No tool calls until that summary is written.

## Decisions
- JD Check abandoned — GitHub Actions quota too expensive
- Glassdoor, ZipRecruiter, Bayt excluded — high-failure boards
- Anti-bot delay: 4-6s random per site call, non-negotiable
- Global sniper = clinical (strict); India = permissive
- Deployment verified via `python deploy.py` which runs syntax/import gate before push
