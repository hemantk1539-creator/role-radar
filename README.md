# role-radar

> A production job-discovery pipeline that scrapes 20+ sources in parallel, filters to senior QA/QE engineering-leadership roles with surgical precision, and emails a deduplicated digest three times a day — timed to the hours recruiters post in India.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-111%20passing-brightgreen)
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)
![Deploy gate](https://img.shields.io/badge/deploy-test--gated-orange)
![License](https://img.shields.io/badge/license-MIT-green)

![Sample alert email](docs/sample-alert.png)

*A real digest: senior QA/QE roles matched in the last 24h, bucketed by location, one-click apply links — manufacturing/recruiter/junior noise already stripped out.*

---

## Why this exists

Job hunting for senior engineering-management roles has two problems that compound each other:

1. **The early-applicant window is real.** Recruiters screen the first wave of applicants first; a role you find 48 hours late is a role you've half-lost. Manually refreshing LinkedIn/Naukri across ten cities, four times a day, is not a plan.
2. **Search is noisy.** A query for *"Quality + Manager"* on any Indian job board returns food-quality managers at PepsiCo, weld-quality engineers at L&T, and "immediate-joiner" body-shop reposts — for every actual software QA leadership role.

**role-radar** solves both. It runs three times a day on a schedule tuned to India's posting peaks, pulls from 20+ sources in parallel, and applies a multi-stage filter that keeps EM → Director / Head / Staff / Principal **software** QA/QE roles and silently drops everything else. The result lands in your inbox as a clean, ranked, one-click-apply digest before most candidates have even seen the posting.

It's also a live system I run daily — so it's built like one: every change is test-gated, state is crash-safe, and the scrapers fail soft.

---

## What it does

- **Scrapes** LinkedIn + Indeed (via [`python-jobspy`](https://github.com/Bunsly/JobSpy)) across 10 India locations (9 metros + remote), plus 20+ Greenhouse / Lever / Ashby / Breezy ATS boards and curated RSS/JSON remote-job feeds — all in parallel.
- **Filters** every title through a word-boundary gate: must carry a **seniority** anchor *and* a **domain** anchor, must **not** carry a residency/junk blacklist hit, and must **not** carry a physical/manufacturing/contract block-anchor (`food quality`, `welding`, `semiconductor`, `c2c`, …).
- **Categorizes** each survivor into one of three buckets — `local` (city match), `india_remote` (work-from-anywhere India), or `global_remote` (timezone-agnostic / fully-remote) — using city aliases, remote signals, and residency-restriction detection.
- **Deduplicates** on an MD5 of the job URL plus a `title|company|location` fingerprint, with state persisted across runs on a dedicated branch.
- **Emails** a tiered, color-coded HTML digest via Gmail SMTP — values are HTML-escaped, so titles like *"R&D Quality Manager"* render correctly.

---

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

---

## Engineering highlights

The parts a code reviewer actually cares about:

### 1. Word-boundary matching everywhere (`\b`)
A naïve substring filter blocks `salesforce` when you blacklist `sales`, and snipes a legit role titled *"…Associated…"* when you screen `associate`. Every match in the pipeline uses `\b`-anchored regex (`has_word_match`). It's enforced as a project invariant and regression-tested — `test_blacklist_substring_does_not_snipe` exists specifically so this never regresses again.

### 2. Signal quality is a precision/recall decision, made explicitly
The India pipeline is *permissive by design* (it has to be, to catch fast-moving postings). Permissiveness produces relevance noise, so noise is filtered with a **phrase-based negative-domain list** (`india_block_anchors`) applied at a single extracted, unit-tested gate (`india_is_applicable`). The design choices are deliberate and documented:
- **Phrases, not bare words** — `"food quality"` is blocked; `"food"` is not, so a real QA role at a food-delivery startup survives.
- **`motor` is *not* a block-anchor** — it would kill *motor-insurance* software-QA roles (a real BFSI vertical). Precision was traded away here on purpose to protect recall.
- **Company-name blocklisting was evaluated and rejected** — conglomerates like L&T / Schneider / AMD run real software arms, so blocking by company would drop good roles. The filter stays title-based.

### 3. State is crash-safe, and `main` stays clean
`job_history.json` is rewritten every run. Committed to `main`, it caused a merge conflict on every scheduled run between deployments. It now lives on an **orphan `data` branch**: the Action restores history from `data` before each run and writes it back after — `main` is never touched by automation. Sniped (rejected) roles are persisted too, so junior/blacklisted titles dedup and don't resurface day after day.

### 4. The schedule is external, on purpose
GitHub's native `schedule:` cron is best-effort and routinely runs late — unacceptable when the whole point is to be an *early* applicant. Instead the workflow exposes `workflow_dispatch` and an external scheduler (cron-job.org) pings it at precise UTC times chosen to hit India's morning, afternoon, and evening posting bursts.

### 5. Deployment is a quality gate, not a `git push`
Direct pushing is forbidden. `deploy.py` is the only path, and it refuses to ship code that doesn't pass (see [Deployment](#deployment)).

### 6. Fails soft, never silent
Every fetcher is wrapped with typed exception handling and a timeout; one dead ATS board or a malformed feed degrades that source to zero results and logs it — it never takes down the run. A monkey-patch around `jobspy`'s country parser keeps 3-part international locations from crashing the scrape.

---

## Test suite

**111 tests across 7 files, ~1.6s runtime.** Coverage spans the filter logic, fetcher integrations (mocked at the HTTP boundary), the categorization decision tree, output-schema contracts, dedup determinism, and performance SLAs at pipeline scale. Business-logic functions live at module level specifically so they're unit-testable in isolation.

```bash
uv run python -m pytest tests/ -v
```

Tests are a **deployment gate** — `deploy.py` blocks the push if a single one fails. Full per-test reference (every class, every parametrized case, every invariant) is in **[TEST_SUITE.md](TEST_SUITE.md)**.

---

## Tech stack

`Python 3.10+` · `uv` · [`python-jobspy`](https://github.com/Bunsly/JobSpy) · `feedparser` · `requests` · `pyyaml` · `pytest` · GitHub Actions · Gmail SMTP

---

## Run it locally

```bash
# 1. Install dependencies (uv)
uv pip install -r requirements.txt

# 2. Configure — edit search terms, cities, filters, and sources
#    All strategy lives in job_alert_config.yaml (no secrets in it).
$EDITOR job_alert_config.yaml

# 3. Provide the one secret via environment variable (never hardcoded)
export GMAIL_APP_PASSWORD="your-gmail-app-password"   # PowerShell: $env:GMAIL_APP_PASSWORD="..."

# 4. Run once
python job_alert_bot_github.py
```

Configuration is **100% data-driven** — seniority/domain anchors, block-anchors, city aliases, source URLs, ATS tokens, email tiering, and freshness windows are all in `job_alert_config.yaml`. No strategy is hardcoded in the Python (a `deploy.py` audit enforces this).

---

## Deployment

`deploy.py` is the **only** authorized push path. A commit message is required. Every deploy runs, in order:

```bash
python deploy.py "feat: add Wellfound RSS source"
```

| Step | Gate |
|------|------|
| 1 | **Syntax / import check** on the bot module |
| 2 | **Full pytest suite** — any failure blocks the push |
| 3 | **Sanity run** — restores live history, executes the bot end-to-end |
| 4 | **Hardcode audit** — fails if strategy data (long literal lists) leaked into the `.py` |
| 5 | `git stash → pull --rebase → pop → commit → push → server verify` |

If any gate fails, nothing ships.

---

## Project layout

```
role-radar/
├── job_alert_bot_github.py   # the pipeline (fetch → filter → categorize → dedup → email)
├── job_alert_config.yaml     # 100% of the strategy: anchors, sources, cities, tiers
├── deploy.py                 # the only authorized push path (test-gated)
├── tests/                    # 111 tests across 7 files
├── .github/workflows/        # workflow_dispatch action (external-cron triggered)
├── docs/sample-alert.png     # sample digest
├── TEST_SUITE.md             # full test reference
└── README.md
                              # job_history.json lives on the orphan `data` branch
```

---

## Roadmap / parked

- **Naukri** — parked (returns 406/reCAPTCHA on cloud IPs since early 2026). The integration code is intact and re-enables by removing one entry from `blocked_sites`; a Playwright-based probe is the next investigation.
- Several config keys (`global_hubs`, `india_sites`, deep-scrape hubs) are intentionally **parked + annotated** in the YAML for planned features — kept, not deleted.

---

## License

[MIT](LICENSE)
