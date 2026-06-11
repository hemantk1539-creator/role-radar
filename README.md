# role-radar

> A production job-discovery pipeline that scrapes 20+ sources in parallel, filters to senior QA/QE engineering-leadership roles with surgical precision, and emails a deduplicated digest three times a day, timed to the hours recruiters post in India.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-114%20passing-brightgreen)
![CI](https://github.com/hemantk1539-creator/role-radar/actions/workflows/job_bot_action.yml/badge.svg)
![Deploy gate](https://img.shields.io/badge/deploy-test--gated-orange)
![License](https://img.shields.io/badge/license-MIT-green)

![Sample alert email](docs/sample-alert.png)

*A real digest: senior QA/QE roles matched in the last 24h, bucketed by location, with one-click apply links. Manufacturing, recruiter, and junior noise is already stripped out.*

## Contents

- [Why this exists](#why-this-exists)
- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [What gets kept vs dropped](#what-gets-kept-vs-dropped)
- [Engineering highlights](#engineering-highlights)
- [Test suite](#test-suite)
- [Tech stack](#tech-stack)
- [Run it locally](#run-it-locally)
- [Deployment](#deployment)
- [Limitations](#limitations)
- [Roadmap](#roadmap)

## Why this exists

Job hunting for senior engineering-management roles has two problems that compound each other:

1. **The early-applicant window is real.** Recruiters screen the first wave of applicants first, so a role you find 48 hours late is a role you have half-lost. Manually refreshing LinkedIn and Naukri across ten cities, several times a day, is not a plan.
2. **Search is noisy.** A query for *"Quality + Manager"* on any Indian job board returns food-quality managers at PepsiCo, weld-quality engineers at L&T, and "immediate-joiner" body-shop reposts for every actual software QA leadership role.

**role-radar** solves both. It runs three times a day on a schedule tuned to India's posting peaks, pulls from 20+ sources in parallel, and applies a multi-stage filter that keeps EM, Senior EM, Director, Head, Staff, and Principal **software** QA/QE roles while silently dropping everything else. The result lands in your inbox as a clean, ranked, one-click-apply digest before most candidates have even seen the posting.

It is also a live system I run daily, so it is built like one: every change is test-gated, state is crash-safe, and the scrapers fail soft.

## What it does

- **Scrapes** LinkedIn and Indeed (via [`python-jobspy`](https://github.com/Bunsly/JobSpy)) across 10 India locations (9 metros plus remote), plus 20+ Greenhouse / Lever / Ashby / Breezy ATS boards and curated RSS/JSON remote-job feeds, all in parallel.
- **Filters** every title through a word-boundary gate: it must carry a **seniority** anchor *and* a **domain** anchor, must **not** carry a residency/junk blacklist hit, and must **not** carry a physical/manufacturing/contract block-anchor (`food quality`, `welding`, `semiconductor`, `c2c`, and so on).
- **Categorizes** each survivor into one of three buckets: `local` (city match), `india_remote` (work-from-anywhere India), or `global_remote` (timezone-agnostic / fully-remote), using city aliases, remote signals, and residency-restriction detection.
- **Deduplicates** on an MD5 of the job URL plus a `title|company|location` fingerprint, with state persisted across runs on a dedicated branch.
- **Emails** a tiered, color-coded HTML digest via Gmail SMTP. Values are HTML-escaped, so titles like *"R&D Quality Manager"* render correctly.

## How it works

```
                 cron-job.org  ──(workflow_dispatch ping)──►  GitHub Actions
                 06:00 / 11:30 / 16:30 UTC                          │
                 (11:30 / 17:00 / 22:00 IST)                        │
                                                                    ▼
                                    ┌───────────────────────────────────────────────┐
   data branch  ──restore──────────►  job_alert_bot_github.py                        │
   (job_history.json)               │                                               │
        ▲                           │  1. PARALLEL FETCH  (ThreadPoolExecutor)       │
        │                           │     • global intel: ATS + RSS + JSON hubs      │
        │                           │     • India: jobspy × 10 locations × terms     │
        │                           │  2. FRESHNESS    drop postings > 24h (72h glob)│
        │                           │  3. APPLICABILITY  india_is_applicable():      │
        │                           │       blacklist? seniority∧domain? block-anchor│
        │                           │  4. DEDUP        MD5(url) + fingerprint         │
        │                           │  5. CATEGORIZE   local / india_remote / global │
        │                           │  6. FINALIZE     snipe junior + blacklist      │
        │                           └───────────────┬───────────────────────────────┘
        │                                           │
        └──────save (new uids+fps)─────────┐        ▼
                                           │   Gmail SMTP  ──►  tiered HTML digest
                                           │
                                    (history written back to data branch)
```

The pipeline is two engines that converge: a **global remote** engine (direct ATS/RSS/JSON hub crawl) and an **India** engine (`jobspy` across metros). Both feed the same applicability gate, dedup, and categorizer, then split into per-bucket emails.

## What gets kept vs dropped

The filter is title-based and deliberately tuned for precision without sacrificing the senior software-QA roles that matter. A few representative calls:

| Title | Verdict | Why |
|-------|---------|-----|
| `Engineering Manager, Quality Engineering` | ✅ kept | seniority (`manager`) + domain (`quality`), no blocks |
| `Director of Quality Engineering` | ✅ kept | a senior software-QA leadership title |
| `Test Manager, Motor Insurance` | ✅ kept | `motor` is deliberately **not** blocked, to protect BFSI/insurance software-QA roles |
| `Head of Quality, Consumer Products` | ❌ dropped | `consumer products` block-anchor (physical goods) |
| `Food Quality Control Manager` | ❌ dropped | `food quality` block-anchor |
| `QA Lead (Immediate Joiners, C2C)` | ❌ dropped | `c2c` block-anchor (body-shop contract) |
| `Senior Associate, QA Testing` | ❌ dropped | `associate` blacklist (below the EM bar) |

The matching is all word-boundary anchored, so `sales` never blocks `salesforce` and `associate` never trips on `associated`.

## Engineering highlights

The parts a code reviewer actually cares about:

### 1. Word-boundary matching everywhere (`\b`)
A naive substring filter blocks `salesforce` when you blacklist `sales`, and snipes a legitimate role titled *"...Associated..."* when you screen `associate`. Every match in the pipeline uses `\b`-anchored regex (`has_word_match`). It is enforced as a project invariant and regression-tested; `test_blacklist_substring_does_not_snipe` exists specifically so this never regresses.

### 2. Signal quality is a precision/recall decision, made explicitly
The India pipeline is *permissive by design* (it has to be, to catch fast-moving postings). Permissiveness produces relevance noise, so noise is filtered with a **phrase-based negative-domain list** (`india_block_anchors`) applied at a single extracted, unit-tested gate (`india_is_applicable`). The design choices are deliberate and documented:
- **Phrases, not bare words.** `"food quality"` is blocked; `"food"` is not, so a real QA role at a food-delivery startup survives.
- **`motor` is deliberately not a block-anchor.** It would kill *motor-insurance* software-QA roles (a real BFSI vertical). Precision was traded away here on purpose, to protect recall.
- **Company-name blocklisting was evaluated and rejected.** Conglomerates like L&T, Schneider, and AMD run real software arms, so blocking by company would drop good roles. The filter stays title-based.

### 3. State is crash-safe, and `main` stays clean
`job_history.json` is rewritten every run. Committed to `main`, it caused a merge conflict on every scheduled run between deployments. It now lives on an **orphan `data` branch**: the Action restores history from `data` before each run and writes it back after, so `main` is never touched by automation. Sniped (rejected) roles are persisted too, so junior and blacklisted titles dedup and do not resurface day after day.

### 4. The schedule is external, on purpose
GitHub's native `schedule:` cron is best-effort and routinely runs late, which is unacceptable when the whole point is to be an *early* applicant. Instead the workflow exposes `workflow_dispatch`, and an external scheduler (cron-job.org) pings it at precise UTC times chosen to hit India's morning, afternoon, and evening posting bursts.

### 5. Deployment is a quality gate, not a `git push`
Direct pushing is forbidden. `deploy.py` is the only path, and it refuses to ship code that does not pass (see [Deployment](#deployment)).

### 6. Fails soft, never silent
Every fetcher is wrapped with typed exception handling and a timeout. One dead ATS board or a malformed feed degrades that source to zero results and logs it; it never takes down the run. A monkey-patch around `jobspy`'s country parser keeps 3-part international locations from crashing the scrape.

## Test suite

**114 tests across 7 files, ~1.6s runtime.** Coverage spans the filter logic, fetcher integrations (mocked at the HTTP boundary), the categorization decision tree, the email HTML build, output-schema contracts, dedup determinism, and performance SLAs at pipeline scale. Business-logic functions live at module level specifically so they are unit-testable in isolation.

```bash
uv run python -m pytest tests/ -v
```

Tests are a **deployment gate**: `deploy.py` blocks the push if a single one fails. The full per-test reference (every class, every parametrized case, every invariant) is in **[TEST_SUITE.md](TEST_SUITE.md)**.

## Tech stack

`Python 3.10+` · `uv` · [`python-jobspy`](https://github.com/Bunsly/JobSpy) · `feedparser` · `requests` · `pyyaml` · `pytest` · GitHub Actions · Gmail SMTP

## Run it locally

```bash
# 1. Install dependencies (uv)
uv pip install -r requirements.txt

# 2. Configure: edit search terms, cities, filters, and sources.
#    All strategy lives in job_alert_config.yaml (no secrets in it).
$EDITOR job_alert_config.yaml

# 3. Provide the one secret via environment variable (never hardcoded)
export GMAIL_APP_PASSWORD="your-gmail-app-password"   # PowerShell: $env:GMAIL_APP_PASSWORD="..."

# 4. Run once
python job_alert_bot_github.py
```

Configuration is **100% data-driven**: seniority/domain anchors, block-anchors, city aliases, source URLs, ATS tokens, email tiering, and freshness windows all live in `job_alert_config.yaml`. No strategy is hardcoded in the Python, and a `deploy.py` audit enforces that.

## Deployment

`deploy.py` is the **only** authorized push path, and a commit message is required:

```bash
python deploy.py "feat: add Wellfound RSS source"
```

Every deploy runs, in order:

| Step | Gate |
|------|------|
| 1 | **Syntax / import check** on the bot module |
| 2 | **Full pytest suite.** Any failure blocks the push |
| 3 | **Sanity run.** Restores live history, executes the bot end-to-end |
| 4 | **Hardcode audit.** Fails if strategy data (long literal lists) leaked into the `.py` |
| 5 | `git stash`, `pull --rebase`, `pop`, `commit`, `push`, then server verify |

If any gate fails, nothing ships.

## Project layout

```
role-radar/
├── job_alert_bot_github.py   # the pipeline (fetch, filter, categorize, dedup, email)
├── job_alert_config.yaml     # 100% of the strategy: anchors, sources, cities, tiers
├── deploy.py                 # the only authorized push path (test-gated)
├── tests/                    # 114 tests across 7 files
├── .github/workflows/        # workflow_dispatch action (external-cron triggered)
├── docs/sample-alert.png     # sample digest
├── TEST_SUITE.md             # full test reference
└── README.md
```

`job_history.json` is not on `main`; it lives on the orphan `data` branch (see [State is crash-safe](#3-state-is-crash-safe-and-main-stays-clean)).

## Limitations

Honest constraints, by design or circumstance:

- **Title-based filtering catches the clear cases, not 100%.** A generically-titled industrial role (for example, plain "Manager, Quality" at a hardware firm with no give-away keyword) can still slip through. That is an accepted precision/recall trade: a stricter rule would also drop legitimate "Director of Quality" software roles, which matters more.
- **Source-dependent.** It relies on `python-jobspy` and public ATS/RSS endpoints. If a board changes its API or blocks cloud IPs (as Naukri did), that source degrades to zero until the integration is updated.
- **Single-recipient by design.** This is a personal pipeline, not a multi-tenant service.
- **No public live demo.** It emails a private inbox on a schedule; the sample screenshot above is the artifact.

## Roadmap

- **Naukri** is parked (it returns 406/reCAPTCHA on cloud IPs since early 2026). The integration code is intact and re-enables by removing one entry from `blocked_sites`; a Playwright-based probe is the next investigation.
- Several config keys (`global_hubs`, `india_sites`, deep-scrape hubs) are intentionally **parked and annotated** in the YAML for planned features. They are kept, not deleted.

## License

[MIT](LICENSE)
