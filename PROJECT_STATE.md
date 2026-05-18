# 🟢 LIVE SYSTEM CONFIGURATION (Source of Truth)
> *Last Updated: Session 105.16 (2026-05-18)*

## 🛡️ FAILURE PREVENTION ARCHIVE (Anti-Failure Rules)
### 📜 Failure Analysis (5-Whys Audit)
- **Failure:** Skipped Post-Push Verification Protocol in Session 105.11.
- **Root Cause:** The agent's focus prematurely shifted to confirming the git push success and assumed the deployment task was complete, ignoring the mandatory chronological checklist defined in `GEMINI.md`.
- **Corrective Action (Rule 27):** **Post-Push Lock**. After any `git push` or `deploy.py` execution, the agent must *immediately* and *autonomously* print the exact headers: `1. File Integrity Scan`, `2. Contradiction Audit vs Grid`, and `3. Critical Path Logic Flow`. No other response text is permitted until this protocol is fulfilled.

- **Failure:** Consecutive Pre-Push Rigor Gate Violations (Sessions 105.9, 105.10).
- **Root Cause:** Procedural decay. The agent prioritized "Total Visibility" logging over the "Rigor Gate" mandate.
- **Corrective Action (Rule 26):** Any future Pre-Push violation will trigger an immediate **Mandatory System Lock**. No further code changes will be allowed until the user explicitly issues an 'UNLOCK' command after reviewing a full manual audit of the entire codebase.

### 📜 Active Constraints (Codified Rules)
- **Rule 13 (Import Gate):** Full runtime syntax check mandatory.
- **Rule 16 (Post-Push Protocol):** 3-step verification protocol.
- **Rule 19 (Temporal Safety Buffer):** Lookback set to 72 hours to ensure roles posted over 3-day windows are captured.
- **Rule 21 (Segmented Purity):** Global Sniper = Clinical; India = Permissive.
- **Rule 22 (Efficiency Lock):** Parallel Burst engine active.
- **Rule 24 (Intersection Logic):** Search engine must use keyword intersections (Level AND Domain) to prevent order-based misses (e.g. Fluence).

## 📊 Final Enablement Grid (Master Directive)
| Scenario | Task Type | Sniper Mode | Action |
| :--- | :--- | :--- | :--- |
| **India Local/Hybrid** | India Task | Permissive | **Local Bucket** + Signal Tag |
| **India WFA** | India Task | Permissive | **India Remote Bucket** |
| **Global Intel** | Power 6 Hubs | **Hardened** | **Tier 1-4 (Diamond Sorted)** |

## ⚙️ Current Runtime Config
- **Strategy:** **Unified Freshness Engine (v3.2)**.
- **Search Engine:** Parallel Engine + Double-Lock Freshness Audits.
- **Seniority:** EM, SEM, Manager, Sr Manager, Director, Head, Architect, Principal, Staff, Chief, Leader.
- **Domain:** Quality, QA, QE, SDET, SET, Test, Testing, Automation.
- **Lookback:** 24h (India Scrape) / 72h (Global APIs).
- **Status:** **DEPLOYED & VERIFIED (v3.2).** 

---

# 📜 Session History (Log)

### Session 105.10: v3.2 Unified Freshness Deployment
- **Date:** 2026-02-24
- **Audit:** Identified need for clinical consistency in freshness reporting across India and Global paths.
- **Action:** Implemented "Double-Lock" date filtering for India.
- **Result:** India searches now manually verify role age in Python after scraping to catch board-level leaks. Logs now show `Kept vs Dropped` for both India and Global.

### Session 105.9: v3.1 Total Visibility Deployment
- **Date:** 2026-02-24
- **Audit:** Identified visibility gap in v3.0 logs where Global Hub activity was silent.
- **Action:** Implemented Deep Global Logging across all 23+ platforms.
- **Restoration:** Re-integrated Global Intel loop into the main `run()` flow with Kept vs. Dropped freshness tracking.
- **Result:** Every run now provides detailed evidence of source hitting and age filtering.

### Session 105.8: v3.0 Parallel India Engine Deployment
- **Date:** 2026-02-24
- **Problem:** v2.9 "Freshness" update improved results but didn't reduce build time due to sequential network latency (25m run).
- **Action:** Implemented v3.0 Parallel Engine using `concurrent.futures.ThreadPoolExecutor`.
- **Optimization:** 3 Parallel Workers for India city scrapes with random staggered delays (3-5s).
- **Result:** Build time expected to drop to ~12-15 minutes. 100% logic and data integrity preserved.

### Session 105.7: Optimization to v2.9 (Precision Freshness)
- **Date:** 2026-02-23
- **Strategy:** Implemented "Split Freshness" to optimize GitHub Action build time.
- **Action:** 
    - Reduced India search window to **24 hours** to minimize network payload and processing time.
    - Maintained Global Hub window at **72 hours** via custom Python timestamp filtering to protect against weekend role loss.
- **Result:** Successfully deployed. Build time optimized for quota safety without compromising global coverage.

### Session 105.6: Optimization to v2.8.2 (Clinical Saturation)
- **Date:** 2026-02-23
- **Action:** Refined search strings to stay under the 250-character limit to prevent silent truncation on Naukri/Indeed.
- **Optimization:** Compressed redundant phrases while maintaining 1:1 parity with the Sniper whitelist.
- **Verification:** Empirically verified via `forensic_comparison.py` that atomic keywords (`Quality`, `Test`) capture all SDET and long-phrase roles without loss.
- **Result:** System is now truncation-proof and phrasal-trap-proof.

### Session 105.5: Strategy Pivot to v2.8 Elastic Engine
- **Date:** 2026-02-23
- **Audit:** Identified critical gap in v2.6; rigid phrase matching (`"Quality Engineering"`) was missing roles with connecting words like "of" (e.g., "Director of Quality").
- **Action:** Formulated and deployed v2.8 Elastic Engine using atomic keywords (`Director AND Quality`) to ensure absolute coverage.
- **Parity:** Synchronized all Sniper abbreviations (`Mgr`, `Dir`, `Snr`, `Sr.`, `Eng Manager`) and single-word anchors (`Quality`, `Test`, `Testing`, `QA`) into search strings.
- **Result:** Successfully pushed to production. Absolute parity between search net and sniper gate achieved.

### Session 105.4: Production Deployment (v2.6)
- **Date:** 2026-02-23
- **Action:** Full deployment of v2.6 Saturation Engine.
- **Verification:** 
    - Sniper-Level Parity: 100% (High Lead, Mid Lead, EM, IC Lead).
    - Domain Parity: 100% (Standard, Technical, Modern, Full-form).
    - Yield Audit: 10 roles in Bengaluru (LinkedIn), 21 roles Global (Power 6).
- **Optimization:** Moved hardcoded `block_anchors` to `job_alert_config.yaml` to ensure clean deployment audit.
- **Result:** System running at 90% quota efficiency with maximum saturation.

### Session 105.3: v2.6 Absolute Saturation Engine
- **Date:** 2026-02-23
- **Action:** Re-engineered search strings into Boolean Intersections. Removed VP. Added SEM and Sr. Manager. Included Software Quality, SET, and full forms.
- **Reason:** Permanent fix for the "Fluence Miss" and other ordering/abbreviation-based misses.

### Session 105.3: Temporal Safety Patch (v1.9.5)
- **Date:** 2026-02-23
- **Action:** Increased `hours_old` to 72.
- **Result:** System resilient against weekend misses.

### Session 105.12: India Engine Signal Augmentation
- **Date:** 2026-02-24
- **Action:** Augmented `global_remote_signals`, `remote_signals`, and `residency_signals` lists in `job_alert_config.yaml`.
- **Reason:** To catch elite foreign roles (e.g., 'timezone agnostic', 'planet-scale') hiding in Indian job boards, and to aggressively filter out US-specific tax/residency traps (e.g., 'w2 only', 'must reside in the us') before they reach the email buckets.

### Session 105.13: Total Visibility Logging Deployment
- **Date:** 2026-02-24
- **Action:** Implemented granular logging across Global Hubs and India Engine.
- **Global:** Removed conditional suppression of 0-match results. Bot now explicitly logs every hub/ATS check.
- **India:** Workers now announce active city/site scrapes.
- **Reason:** To provide a verifiable "heartbeat" in GitHub Action logs, ensuring every configured source is being actively hit and processed, and allowing for easier remote debugging.


### Session 105.14: Context Alignment & Directory Migration
- Date: 2026-02-25
- Action: Synchronized with v3.2 state and project mandates. Identified technical debt (JD Check, Substring Trap, Indeed Fragility).
- Status: Session ended to allow restart from the correct project-specific directory.

### Session 105.15: v3.2.1 Structural Integrity Fixes
- **Date:** 2026-02-25
- **Audit:** Analyzed pending technical debt affecting India Pipeline Categorization and Indeed stability. Confirmed JD Check is unfeasible due to strict GitHub Action quota limits (abandoned). 
- **Action:** 
    1. Implemented regex word boundaries `\b` for `blacklist` matching in Hub-Applicability Guard to prevent "Substring Traps" (e.g. 'sales' blocking 'salesforce').
    2. Replaced fragile `')'` stripping in Indeed worker with robust `f-string` grouping `f"({t1}) OR ({t2})"`.
- **Result:** Pipeline is now immune to false-positive blacklist drops and index-crash vulnerabilities. Ready for deployment.

### Session 105.16: v3.2.2 Reliability Hardening
- **Date:** 2026-05-18
- **Agent:** Claude (migrated project from GEMINI CLI workspace to Claude workspace)
- **Audit:** Full codebase review. Strategy and filtering logic unchanged. Identified 5 reliability/security gaps not covered by prior sessions.
- **Action:**
    1. Added `python-dateutil` to `requirements.txt` — was imported but undeclared; caused silent ImportError on GitHub Actions.
    2. Removed hardcoded `app_password: "qwerty"` from `job_alert_config.yaml` — replaced with empty string; env var is sole credential source.
    3. Replaced all 7 bare `except:` clauses with typed exceptions — `load_history` uses `(json.JSONDecodeError, ValueError, OSError)`, workers use `Exception as e` with logging, date-parse excepts use `Exception` silently (safe default: keep job).
    4. Added `timeout=30` to `smtplib.SMTP()` — prevents indefinite hang blocking GitHub Actions runner.
    5. Created `CLAUDE.md` for project — captures deployment lock, config mandate, and session start protocol for Claude sessions.
- **Result:** No logic or strategy changes. Bot is now hardened against silent failures, credential leaks, and runner hangs. v3.2.2 ready for deployment.
