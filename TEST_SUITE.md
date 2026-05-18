# Job Alert Bot — Test Suite Reference

**95 tests · 7 files · 100% pass rate**
Run: `uv run python -m pytest tests/ -v`

---

## Architecture

```
tests/
  conftest.py           shared constants + fixtures
  test_filters.py       title qualification, word boundary, finalize gate
  test_history.py       persistence layer — load + save
  test_fetchers.py      HTTP fetcher integrations (JSON, RSS, ATS)
  test_categorization.py  3-bucket location routing
  test_contracts.py     output schema + deduplication integrity
  test_performance.py   SLA assertions at pipeline scale
```

All business logic functions are tested at module level — no internal mocking. HTTP calls and filesystem I/O are the only mocked boundaries.

---

## conftest.py — Shared Fixtures

### Constants

| Name | Value | Purpose |
|------|-------|---------|
| `LEVELS` | `["manager", "director", "head", "lead", "principal", "staff", "senior manager"]` | Seniority terms for `is_match` |
| `DOMAINS` | `["qa", "qae", "qe", "quality", "test", "automation", "sdet"]` | Domain terms for `is_match` |
| `BLOCK_ANCHORS` | `["product", "project", "program", "sales", "marketing", "ops"]` | Title killers for `is_match` |
| `BLACKLIST` | `["recruiter", "staffing", "sales", "agency"]` | Finalize-gate word blacklist |
| `REMOTE_SIGNALS` | `["remote", "wfh", "work from home", "wfa"]` | India-remote triggers |
| `GLOBAL_REMOTE_SIGNALS` | `["timezone agnostic", "anywhere", "fully remote", "worldwide"]` | Global-remote triggers |
| `RESIDENCY_SIGNALS` | `["must reside", "us citizen", "uk citizen", "authorized to work"]` | Drop signals |
| `INDIA_CITY_ALIASES` | `["pune", "bangalore", "mumbai", "hyderabad", "chennai", "delhi", "pan india"]` | India city lookup |
| `INDIA_CODE` | `"in"` | Country code for India routing |
| `GLOBAL_LOC` | `"worldwide"` | Country code for global routing |
| `JOB_SCHEMA_KEYS` | `{"title", "company", "location", "job_url", "source"}` | Required output keys |

### Fixtures

| Fixture | Scope | Provides |
|---------|-------|---------|
| `blacklist` | function | `["recruiter", "staffing", "sales", "agency"]` |
| `job_factory` | function | callable: `job_factory(title=..., company=..., location=...)` → job dict |
| `history_file` | function | temp file path via `tmp_path` |
| `save_config` | function | dict with `max_history=10` |

---

## test_filters.py — 38 tests

### TestIsMatch (17 tests)
`is_match(title, levels, domains, block_anchors) → bool`

**Gate logic:** title must have ≥1 level term AND ≥1 domain term AND no block anchor. All matching is case-insensitive with word boundaries.

#### Passing titles (8 parametrized)

| Title | Why it passes |
|-------|--------------|
| `Engineering Manager - QA` | level=manager, domain=qa |
| `Director of Quality Engineering` | level=director, domain=quality |
| `Head of Test Automation` | level=head, domain=test+automation |
| `Senior Manager, SDET` | level=manager, domain=sdet |
| `Staff Engineer - Quality` | level=staff, domain=quality |
| `QA Lead Manager` | level=lead+manager, domain=qa |
| `ENGINEERING MANAGER QA` | case-insensitive match |
| `Principal Automation Engineer` | level=principal, domain=automation |

#### Failing titles (8 parametrized)

| Title | Why it fails |
|-------|-------------|
| `Engineering Manager - Product` | block anchor: "product" |
| `Senior QA Engineer` | no level match (engineer ≠ manager/director/etc) |
| `Product Manager - Quality` | block anchor: "product" |
| `Project Manager QA` | block anchor: "project" |
| `""` | empty string |
| `Software Engineer` | no level, no domain |
| `Sales Manager` | block anchor: "sales" |
| `QA Analyst` | no level match |

#### Edge cases (5 tests)

**test_block_anchor_overrides_valid_match**
```
"Product Quality Engineering Manager" → False
```
Even a title with valid level+domain is killed by block anchor. Anchor wins unconditionally.

**test_block_anchor_substring_does_not_block**
```
anchors = ["prod"]
"Quality Engineering Manager Productivity Tools" → True  (NOT blocked)
"Product Quality Engineering Manager"            → False (blocked by "product")
```
`\bprod\b` does NOT match "productivity" — word boundary after "d" fails at "d+u". This is the v3.2.1 regression test: a past bug where partial anchors incorrectly blocked valid titles.

**test_empty_levels_always_fails** — gate collapses without level list
**test_empty_domains_always_fails** — gate collapses without domain list
**test_empty_block_anchors_does_not_affect_valid_match** — no anchors = no blocking

---

### TestHasWordMatch (12 tests)
`has_word_match(text, terms) → bool`

Wraps `re.search(r"\b<term>\b", text, re.IGNORECASE)` across a list of terms. Returns True on first match.

#### Boundary cases (10 parametrized)

| Text | Terms | Expected | Why |
|------|-------|---------|-----|
| `"head of qa"` | `["qa"]` | True | mid-string exact |
| `"qa manager"` | `["qa"]` | True | start of string |
| `"engineering qa"` | `["qa"]` | True | end of string |
| `"QA Manager"` | `["qa"]` | True | case-insensitive |
| `"salesforce automation"` | `["sales"]` | **False** | \bsales\b fails at "s+f" boundary — core regression |
| `"qae platform manager"` | `["qa"]` | **False** | qa ≠ qae, word boundary prevents partial match |
| `""` | `["qa"]` | False | empty text |
| `"engineering manager"` | `[]` | False | empty term list |
| `"recruiter staffing firm"` | `["sales"]` | False | no match |
| `"head of sales quality"` | `["sales", "qa"]` | True | multi-term, first match wins |

**test_hyphenated_compound_does_not_bleed**
```
"lead-free solder engineer" + ["lead"] → True
```
`\b` matches at hyphen boundaries — "lead" before "-" has a word boundary. This is correct and expected behavior.

**test_multiple_terms_returns_true_on_first_match**
```
"qa manager" + ["sdet", "qa", "automation"] → True (matches on "qa", never evaluates "automation")
```

---

### TestFinalizeList (19 tests)
`finalize_list(jobs, blacklist) → (clean_list, sniped_list)`

Two-stage gate: (1) blacklist word-boundary check on title+company+location, (2) junior role sniper via regex.

**test_empty_list_returns_two_empty_lists** — returns `([], [])`, no crash

**test_clean_role_passes_through** — "Engineering Manager - QA" → clean=1, sniped=0

**test_multiple_clean_roles_all_pass** — 3 clean titles → clean=3, sniped=0

#### Junior/associate sniper (4 parametrized)

| Title | sniped_reason |
|-------|--------------|
| `Junior QA Manager` | `Junior/Associate Role` |
| `Trainee Quality Manager` | `Junior/Associate Role` |
| `Associate Test Manager` | `Junior/Associate Role` |
| `Assistant Engineering Manager` | `Junior/Associate Role` |

#### Senior/lead exception (2 parametrized)

| Title | Result |
|-------|--------|
| `Senior Associate QA Manager` | passes — "Senior" prefix overrides "Associate" |
| `Lead Associate Engineering Manager` | passes — "Lead" prefix overrides "Associate" |

#### Blacklist field coverage (3 tests)

| Field | Input | Outcome |
|-------|-------|---------|
| title | `"Sales QA Manager"` | sniped, reason contains "Blacklist" |
| company | `"Recruiter Corp"` | sniped |
| location | `"Staffing Agency, Mumbai"` | sniped |

**test_blacklist_substring_does_not_snipe**
```
company = "Salesforce" + blacklist = ["sales"] → clean=1, sniped=0
```
Word boundary prevents "sales" matching inside "Salesforce". Mirrors the `has_word_match` regression above.

**test_mixed_list_correctly_split**
```
4 jobs: 1 clean EM, 1 Junior QA, 1 Director, 1 Recruiter company
→ clean=2, sniped=2
```

**test_sniped_job_has_reason_field** — `sniped_reason` key present on sniped jobs
**test_clean_job_has_no_sniped_reason** — `sniped_reason` key absent on clean jobs

---

## test_history.py — 9 tests

### TestLoadHistory (5 tests)
`load_history(path) → list`

| Test | Condition | Expected |
|------|-----------|---------|
| `test_returns_empty_list_when_file_absent` | file does not exist | `[]` |
| `test_returns_empty_list_on_corrupt_json` | file contains `"not json"` | `[]` |
| `test_returns_empty_list_on_empty_json_array` | file contains `[]` | `[]` |
| `test_returns_correct_data_from_valid_file` | valid JSON array | correct data returned |
| `test_returns_empty_list_on_oserror` | mocked OSError on open | `[]` |

All failure modes return `[]` — pipeline never crashes on bad history state.

### TestSaveHistory (4 tests)
`save_history(history, path, max_history=2000) → None`

**test_saves_history_correctly** — written file is valid JSON, contains expected entries

**test_trims_to_max_history_limit** — 15 entries written with max_history=10 → file contains exactly 10

**test_keeps_newest_entries_when_trimming**
Critical behavioral contract: when trimming, the NEWEST entries survive, not the oldest. Verifies `history[-max_history:]` semantics — oldest entries are discarded first.

**test_default_max_history_is_2000** — calling without max_history arg → file contains all 2000 entries

---

## test_fetchers.py — 21 tests

All HTTP calls mocked at `requests.get` and `feedparser.parse` boundaries only. Internal parsing logic tested against realistic payloads.

### TestFetchJson (6 tests)
`fetch_json(source, url, levels, domains, block_anchors) → list[dict]`

| Test | Mock | Expected |
|------|------|---------|
| happy path | 200 + matching payload | 1 result, correct title |
| non-matching title | 200 + "Product Manager" | `[]` |
| company fallback chain | `company` key (not `companyName`) | `results[0]["company"] == "FallbackCo"` |
| 404 | status=404 | `[]` |
| network error | `Exception("Connection refused")` | `[]` |
| schema contract | 200 + matching payload | `JOB_SCHEMA_KEYS ⊆ result.keys()` |

The **company fallback chain** test verifies the key resolution order: `companyName → company_name → company → source`. This catches silent regressions where a refactor breaks field mapping for a specific API format.

### TestFetchRss (4 tests)
`fetch_rss(source, url, levels, domains, block_anchors) → list[dict]`

| Test | Mock | Expected |
|------|------|---------|
| happy path | matching entry dict | 1 result |
| non-matching title | "Product Manager" entry | `[]` |
| parse exception | `Exception("Parse error")` | `[]` |
| schema contract | matching entry | `JOB_SCHEMA_KEYS ⊆ result.keys()` |

### TestFetchAts (9 tests + 2 schema)
`fetch_ats(platform, company_id, levels, domains, block_anchors) → list[dict]`

Covers 3 ATS platforms, each with a different JSON schema:

#### Platform schema parsing (3 tests)

| Platform | Payload shape | Key extracted |
|----------|--------------|--------------|
| Greenhouse | `{"jobs": [{"absolute_url": ...}]}` | `job_url = absolute_url` |
| Lever | `[{"text": ..., "hostedUrl": ...}]` (root list) | `job_url = hostedUrl` |
| Ashby | `{"jobs": [{"job_url": ...}]}` | `job_url = job_url` |

Lever is the oddball — it returns a list at root, not an object. This test prevents the parser from assuming `response["jobs"]` exists.

| Test | Condition | Expected |
|------|-----------|---------|
| non-matching title | "Product Manager" | `[]` |
| 500 | status=500 | `[]` |
| network error | `Exception("Timeout")` | `[]` |
| schema contract | Greenhouse payload | `JOB_SCHEMA_KEYS ⊆ result.keys()` |

---

## test_categorization.py — 12 tests

### TestCategorizeJob
`categorize_job(title, loc, country, india_code, global_loc, remote_signals, global_remote_signals, india_city_aliases, residency_signals) → (bucket, signal) | (None, None)`

**Bucket routing decision tree:**

```
1. Check residency signals in title+location → drop (None, None)
2. Check global remote signals in location → global_remote
3. Check if country == "worldwide" → global_remote
4. Check if country != india_code → if remote signal → global_remote, else → None
5. (India path) Check if india city in location
   → if remote signal → local (city takes priority over remote)
   → else → local
6. (India path) Check if remote signal in location → india_remote
7. Nothing matched → None
```

| Test | Location | Country | Expected bucket | Signal |
|------|----------|---------|----------------|--------|
| india city + remote | `"pune remote"` | `in` | `local` | — |
| india city only | `"pune, india"` | `in` | `local` | — |
| india remote only | `"remote"` | `in` | `india_remote` | `India-WFA` |
| india city + hybrid (no remote) | `"pune hybrid"` | `in` | `local` | `None` |
| global signal in india city | `"pune remote timezone agnostic"` | `in` | `global_remote` | `Global-In-India` |
| worldwide country | `"remote"` | `worldwide` | `global_remote` | `Worldwide Task` |
| global signal, non-india | `"remote fully remote"` | `us` | `global_remote` | — |
| residency in title | title=`"must reside in the us"` | `in` | `None` | `None` |
| residency in location | `"remote us citizen only"` | `in` | `None` | `None` |
| no signal, no city | `"singapore"` | `sg` | `None` | — |
| "pan india" (city alias, no remote) | `"pan india"` | `in` | `local` | — |
| "wfh" (remote signal only) | `"wfh"` | `in` | `india_remote` | — |

**Key invariants validated:**
- City match always wins over remote signal → `local` (not `india_remote`)
- Global signals override city + remote → `global_remote`
- Residency signals are a hard drop, checked first
- "hybrid" alone is not a remote signal → no signal tag

---

## test_contracts.py — 6 tests

### TestJobSchema (3 tests)
Cross-cutting schema validation: every fetcher type must produce dicts containing all required keys.

```python
JOB_SCHEMA_KEYS = {"title", "company", "location", "job_url", "source"}
```

Tests run realistic mocked payloads through the full parse pipeline — not just format checks on hand-constructed dicts.

| Test | Fetcher |
|------|---------|
| `test_fetch_json_output_has_all_required_keys` | `fetch_json` |
| `test_fetch_rss_output_has_all_required_keys` | `fetch_rss` |
| `test_fetch_ats_output_has_all_required_keys` | `fetch_ats` (Greenhouse) |

### TestDeduplicationIntegrity (3 tests)
MD5 hashing properties — correctness of the dedup key generation.

| Test | Assertion |
|------|-----------|
| `test_same_url_always_produces_same_md5` | MD5 is deterministic |
| `test_different_urls_produce_different_hashes` | no hash collision on distinct URLs |
| `test_md5_hash_is_32_chars` | hash format correct (hexdigest = 32 chars) |

These are algorithm-level contracts, not implementation-level: they validate the mathematical properties the dedup system relies on, independent of the calling code.

---

## test_performance.py — 2 tests

### TestPerformance
SLA assertions. If either fails, the pipeline cannot process a full daily run within CI time limits.

**test_finalize_list_5000_jobs_under_2_seconds**
```python
5000 job dicts → finalize_list → must complete in < 2.0s
```
Represents a worst-case daily batch (actual volume typically 50–500). Validates that regex compilation overhead and per-job iteration stay linear at scale.

**test_has_word_match_realistic_blacklist_under_1_second**
```python
50-term blacklist × 10,000 iterations → must complete in < 1.0s
```
50 terms mirrors the real blacklist size. 10,000 iterations represents repeated calls across a full pipeline run with multiple sources. Validates that regex execution per term stays fast at realistic scale — not a microbenchmark, not an unrealistic stress test.

---

## Running the suite

```bash
# Full suite
uv run python -m pytest tests/ -v

# Single file
uv run python -m pytest tests/test_filters.py -v

# Single test
uv run python -m pytest tests/test_filters.py::TestIsMatch::test_block_anchor_substring_does_not_block -v

# Performance only
uv run python -m pytest tests/test_performance.py -v -s

# Fast (exclude performance)
uv run python -m pytest tests/ -v --ignore=tests/test_performance.py
```

## deploy.py integration

`deploy.py` runs the full test suite as part of every deployment. A failing test blocks the push.

```python
result = subprocess.run(["uv", "run", "python", "-m", "pytest", "tests/", "-q"], ...)
if result.returncode != 0:
    raise DeploymentError("Tests failed — push blocked")
```

## Coverage map

| Module area | Test file(s) | Coverage |
|-------------|-------------|---------|
| `is_match` | test_filters, test_contracts | ~100% |
| `has_word_match` | test_filters | ~100% |
| `finalize_list` | test_filters | ~100% |
| `load_history` / `save_history` | test_history | ~100% |
| `fetch_json` | test_fetchers, test_contracts | ~95% |
| `fetch_rss` | test_fetchers, test_contracts | ~95% |
| `fetch_ats` | test_fetchers, test_contracts | ~95% |
| `categorize_job` | test_categorization | ~90% |
| MD5 dedup | test_contracts | 100% |
| Perf SLAs | test_performance | — |
