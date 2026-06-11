# Job Alert Bot - Test Suite Reference

**125 tests - 7 files - 100% pass rate**
Run: `uv run python -m pytest tests/ -v`

---

## Architecture

```
tests/
  conftest.py             shared constants + fixtures
  test_filters.py         title qualification, word boundary, India gate, finalize gate
  test_history.py         persistence layer - load + save
  test_fetchers.py        HTTP fetcher integrations + per-source audit
  test_categorization.py  3-bucket location routing
  test_contracts.py       output schema, dedup integrity, email rendering
  test_performance.py     SLA assertions at pipeline scale
```

The pipeline is split into focused modules and the tests import from them directly:

| Module | Tested by | Functions |
|--------|-----------|-----------|
| `filters.py` | test_filters, test_categorization | `is_match`, `has_word_match`, `india_is_applicable`, `finalize_list`, `categorize_job` |
| `config.py` | test_history | `load_history`, `save_history` |
| `scrapers.py` | test_fetchers, test_contracts | `fetch_json`, `fetch_rss`, `fetch_ats`, `SourceAudit` |
| `emailer.py` | test_contracts | `send_email` |

All business logic is pure and tested at module level - no internal mocking. The only mocked boundaries are HTTP (`requests.get`, `feedparser.parse`), SMTP (`smtplib.SMTP`), and filesystem I/O.

---

## conftest.py - Shared Fixtures

### Constants

| Name | Value | Purpose |
|------|-------|---------|
| `LEVELS` | `["manager", "director", "head", "engineering manager", "em", "staff", "lead", "principal"]` | Seniority terms for `is_match` / `india_is_applicable` |
| `DOMAINS` | `["qa", "quality", "test", "automation", "sdet", "qe"]` | Domain terms |
| `BLOCK_ANCHORS` | `["product", "project manager"]` | Title killers for `is_match` |
| `BLACKLIST` | `["sales", "recruiter", "staffing", "vendor"]` | Finalize-gate + India-gate word blacklist |
| `REMOTE_SIGNALS` | `["remote", "wfh", "work from home", "telecommute"]` | Remote triggers |
| `GLOBAL_REMOTE_SIGNALS` | `["timezone agnostic", "planet-scale", "fully remote", "distributed"]` | Global-remote triggers |
| `RESIDENCY_SIGNALS` | `["us citizen", "security clearance", "w2 only", "must reside in the us"]` | Hard-drop signals |
| `INDIA_CITY_ALIASES` | `["pune", "bengaluru", "bangalore", "gurugram", "mumbai", "delhi", "hyderabad"]` | India city lookup |
| `INDIA_CODE` | `"in"` | Country code for India routing |
| `GLOBAL_LOC` | `"Remote"` | Global search location |
| `JOB_SCHEMA_KEYS` | `{"title", "company", "location", "signal", "job_url", "site", "date"}` | Required output keys |

### Fixtures

| Fixture | Provides |
|---------|----------|
| `levels` / `domains` / `block_anchors` / `blacklist` | the matching constants above |
| `remote_signals` / `global_remote_signals` / `residency_signals` / `india_city_aliases` | the routing constants above |
| `job_factory` | callable: `job_factory(title=..., company=..., location=..., job_url=...)` -> job dict |
| `history_file` | temp file path via `tmp_path` |
| `save_config` | `{"search": {"max_history": 2000}}` |

---

## test_filters.py - 68 tests

### TestIsMatch (21 tests)
`is_match(title, levels, domains, block_anchors) -> bool`  [filters.py]

**Gate logic:** title must have at least one level term AND one domain term AND no block anchor. All matching is case-insensitive with word boundaries (`\b`).

- 8 parametrized passing titles (e.g. `Engineering Manager - QA`, `Director of Quality Engineering`, `Head of Test Automation`, `Principal Automation Engineer`).
- 8 parametrized failing titles (level-only, domain-only, block-anchor hits, empty string).
- `test_block_anchor_overrides_valid_match` - a valid level+domain title is still killed by a block anchor.
- `test_block_anchor_substring_does_not_block` - `\bprod\b` does NOT match "productivity"; the exact `product` anchor does block. (v3.2.1 regression guard.)
- `test_empty_levels_always_fails` / `test_empty_domains_always_fails` / `test_empty_block_anchors_does_not_affect_valid_match`.

### TestHasWordMatch (12 tests)
`has_word_match(text, term_list) -> bool`  [filters.py]

Wraps `re.search(r"\b<term>\b", text, re.IGNORECASE)` across a term list, returns True on first match.

- 10 parametrized boundary cases. The core regression: `"salesforce"` + `["sales"]` -> **False** (word boundary), and `"qae"` is not matched by `["qa"]`.
- `test_hyphenated_compound_does_not_bleed` - `"lead-free"` + `["lead"]` -> True (hyphen is a word boundary; documented expected behavior).
- `test_multiple_terms_returns_true_on_first_match`.

### TestFinalizeList (18 tests)
`finalize_list(job_list, blacklist) -> (clean_list, sniped_list)`  [filters.py]

Two-stage gate: (1) blacklist word-boundary check on title + company + location, (2) junior/associate sniper, both `\b`-anchored.

- Empty list, single clean role, multiple clean roles.
- 4 parametrized junior/associate snipes (`Junior`, `Trainee`, `Associate`, `Assistant`).
- 2 parametrized rescue cases (`Senior Associate ...`, `Lead Associate ...`) pass through.
- Blacklist coverage on title / company / location fields.
- `test_blacklist_substring_does_not_snipe` - `"Salesforce"` survives `["sales"]`.
- `test_asst_abbreviation_gets_sniped` - `"Asst. Manager QA"` is caught by the `asst` blacklist entry (not by `\bassistant\b`).
- `test_substring_does_not_false_snipe_associated` - `"Associated"` is NOT sniped by `associate` (the `\b` fix).
- `sniped_reason` present on sniped jobs, absent on clean jobs.

### TestIndiaIsApplicable (17 tests)
`india_is_applicable(title_str, loc_str, levels, domains, blacklist, block_anchors=()) -> bool`  [filters.py]

The India-side keep/drop gate, extracted from `run()` so it is unit-testable. Mirrors the `is_match` contract: blacklist on title/location, then seniority AND domain, then optional negative-domain block anchors.

- Keeps senior QA/QE roles; drops blacklist hits (title or location), no-seniority, no-domain.
- `test_empty_block_anchors_changes_nothing` - the Step-1 behaviour-identical guarantee.
- `test_block_anchor_drops_when_populated` / `test_block_anchor_leaves_clean_software_role_untouched`.
- `test_wired_anchors_drop_noise` (7 parametrized) - phrase anchors (`food quality`, `supplier quality`, `c2c`, `semiconductor`, `consumer products`, `immediate joiners`) drop manufacturing/contract noise.
- `test_wired_anchors_keep_software_roles` - real software-QA leadership titles survive the same anchor set.

---

## test_history.py - 9 tests
`load_history()` / `save_history(history, config)`  [config.py]

Tests repoint `config.HISTORY_FILE` at a temp path (aliased import: several tests use a local var named `config`).

### TestLoadHistory (5 tests)
File absent, corrupt JSON, empty array, valid file, and a mocked `OSError` all resolve to a safe value - the pipeline never crashes on bad history state.

### TestSaveHistory (4 tests)
Correct write, trim to `max_history`, **newest entries survive when trimming** (`history[-max_h:]` semantics), and the default cap of 2000 when the key is absent.

---

## test_fetchers.py - 24 tests

HTTP mocked at `scrapers.requests.get` and `scrapers.feedparser.parse` only; internal parsing tested against realistic payloads.

### TestFetchJson (6 tests)
`fetch_json(source, url, levels, domains, block_anchors, audit=None) -> list[dict]`

Happy path, non-matching title filtered, company fallback chain (`companyName -> company_name -> company -> source`), 404, network exception, and schema contract (`JOB_SCHEMA_KEYS` subset).

### TestFetchRss (4 tests)
`fetch_rss(...)` - happy path, non-matching filtered, parse exception, schema contract.

### TestFetchAts (7 tests)
`fetch_ats(ats_type, token, levels, domains, block_anchors, audit=None)` - Greenhouse / Lever / Ashby schema parsing (Lever returns a root list, not an object), non-matching filtered, 500, network exception, schema contract.

### TestSourceAudit (7 tests)
`SourceAudit` - the thread-safe per-source outcome collector for the global burst.

- Records `ok` when a source returns roles, `empty` when reachable but zero matches, `error` on non-200 and on exception (JSON and RSS paths).
- `test_ats_label_is_unique_per_ats_type` - the same token under two ATS types (`greenhouse/figma` vs `lever/figma`) does not collide.
- `test_omitting_audit_is_noop` - the defaulted `audit=None` kwarg leaves fetcher behaviour and return value identical (this is what keeps the older fetcher tests valid).

---

## test_categorization.py - 12 tests

### TestCategorizeJob (12 tests)
`categorize_job(title_str, loc_str, country_code, india_code, global_loc, remote_signals, global_remote_signals, india_city_aliases, residency_signals) -> (bucket, signal) | (None, None)`  [filters.py]

12 parametrized routing cases covering the decision tree. Key invariants validated:

- City match wins over a remote signal -> `local` (not `india_remote`).
- Global signals override city + remote -> `global_remote`.
- Residency signals are a hard drop, checked first.
- `"hybrid"` alone is not a remote signal -> no signal tag.
- `worldwide` country code and `wfh`/`pan india` edge cases.

---

## test_contracts.py - 10 tests

### TestJobSchema (3 tests)
Every fetcher type (`fetch_json`, `fetch_rss`, `fetch_ats`) must emit dicts containing all `JOB_SCHEMA_KEYS`, run through the full parse path on realistic mocked payloads.

### TestDeduplicationIntegrity (3 tests)
MD5 key properties: deterministic for the same URL, distinct for different URLs, 32-char hexdigest. Algorithm-level contracts the dedup system relies on.

### TestEmailRendering (4 tests)
`send_email(subject, jobs, config) -> bool`  [emailer.py], with `emailer.smtplib.SMTP` mocked.

- Builds the local and global digests without crashing.
- **HTML-escape regression guard:** `R&D` -> `R&amp;D`, `Acme & Co` -> `Acme &amp; Co` (a local var named `html` once shadowed the `html` module, breaking `esc()` on every email-with-jobs run; this suite crashes on the old code).
- Empty job list returns `False` without sending.
- Env vars (`SENDER_EMAIL` / `RECIPIENT_EMAIL`) override the config values.

---

## test_performance.py - 2 tests

### TestPerformance (2 tests)
SLA assertions at pipeline scale:

- `test_finalize_list_5000_jobs_under_2_seconds` - worst-case daily batch stays under 2s.
- `test_has_word_match_realistic_blacklist_under_1_second` - 50-term blacklist x 10,000 iterations under 1s.

---

## Running the suite

```bash
# Full suite
uv run python -m pytest tests/ -v

# Single file / single test
uv run python -m pytest tests/test_filters.py -v
uv run python -m pytest tests/test_filters.py::TestIsMatch::test_block_anchor_substring_does_not_block -v

# Fast (exclude performance)
uv run python -m pytest tests/ -v --ignore=tests/test_performance.py
```

## deploy.py integration

`deploy.py` runs the full suite as part of every deployment (step 2 of the gate). A single failing test blocks the push.
