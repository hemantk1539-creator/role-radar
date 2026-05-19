# Job Alert Bot

A multi-source job discovery pipeline for senior engineering management roles (EM, Sr. EM, Director, Head of QA/QE/Test/Automation). Runs on GitHub Actions on a schedule, scrapes 20+ sources in parallel, filters with word-boundary regex, deduplicates via MD5, categorizes into 3 location buckets (local / India-remote / global-remote), and emails the results.

![Sample alert email](docs/sample-alert.png)

*Sample digest — 11 matched roles, sniper log showing transparency on filtered-out matches.*

## What it does

- **Scrapes** LinkedIn, Indeed, Naukri (via [python-jobspy](https://github.com/Bunsly/JobSpy)), plus 20+ Greenhouse / Lever / Ashby boards and curated RSS / JSON feeds
- **Filters** titles using word-boundary regex — level AND domain AND no block anchors (prevents "Product Manager — Quality" from matching)
- **Snipes** junior / associate / blacklisted roles (recruiter, staffing, agency) before the email is sent
- **Categorizes** every job into one of 3 buckets — `local`, `india_remote`, or `global_remote` — using city aliases, remote signals, global-remote signals, and residency-restriction detection
- **Deduplicates** with MD5 of the job URL — history persisted on a separate `data` branch (see below)
- **Emails** a sorted digest via Gmail SMTP with deployment trail in the footer

## Architecture

```
┌────────────────────────┐
│  GitHub Actions cron   │
│  (reads data branch)   │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────────────────────────────┐
│  job_alert_bot_github.py                       │
│  ─ Parallel fetch (ThreadPoolExecutor)         │
│  ─ Filter: is_match() — level ∧ domain ∧ ¬block│
│  ─ Categorize: 3-bucket location routing       │
│  ─ Finalize: blacklist + junior sniper          │
│  ─ Dedup: MD5(url) against history             │
└───────────┬────────────────────────────────────┘
            │
            ▼
┌─────────────────────────┐      ┌──────────────┐
│  Gmail SMTP (digest)    │      │  data branch │
└─────────────────────────┘      │  (history)   │
                                 └──────────────┘
```

**Why a separate `data` branch?** `job_history.json` is rewritten on every run. Keeping it on `main` produced merge conflicts every time the GitHub Action ran between manual deployments. Moving it to an orphan `data` branch keeps `main` clean — the Action reads history from `data` before each run and writes updated history back to `data` after, never touching `main`.

## Test suite

95 tests across 7 files, runtime ~1.3s. Covers filter logic, fetcher integrations, categorization decision tree, output schema contracts, dedup integrity, and performance SLAs at pipeline scale. Tests run as a deployment gate — `deploy.py` blocks the push if any fail.

See [TEST_SUITE.md](TEST_SUITE.md) for the full reference (every test class, every parametrized case, every invariant).

```bash
uv run python -m pytest tests/ -v
```

## Running it

```bash
# Install
uv pip install -r requirements.txt

# Configure
cp job_alert_config.yaml.example job_alert_config.yaml   # then edit
export GMAIL_APP_PASSWORD="..."                          # Gmail app password

# Run once
python job_alert_bot_github.py

# Deploy (runs full audit: syntax → tests → sanity → push)
python deploy.py
```

## Deployment

`deploy.py` is the only authorized push path. Every push runs:

1. Syntax / import check on the bot file
2. Full pytest suite — failing tests block the push
3. Sanity run of the bot (validates logic is executable)
4. Hardcode audit (catches accidentally committed strategy data)
5. State file freshness check
6. `git stash → pull --rebase → pop → commit → push → verify`

A pre-push git hook adds a secondary syntax gate that fires even on direct `git push` attempts.

## Stack

`python 3.13` · `uv` · `python-jobspy` · `feedparser` · `requests` · `pyyaml` · `pytest` · GitHub Actions

## License

MIT
