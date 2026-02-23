# Job Alert Bot - Core Mandates

## 1. PRE-PUSH FULL-SYSTEM SANITY
**Trigger:** Before any code push.
**Action:** You must execute a sanity test that validates the **ENTIRE** codebase, not just the modified area.
**Checklist:**
- Verify city-specific iteration for Naukri/Indeed.
- Verify wide-search logic for LinkedIn.
- Verify individual hub iteration for the Global Grid.
- Verify the Universal Hub Guard (blacklist) across different regions.
- Verify Velocity Mode detection based on UTC windows.
**Rule:** If any single part of the system fails the sanity check, the push is ABORTED.

## 2. PRE-PUSH UNIVERSAL AUDIT
**Trigger:** Before performing any `git push`.
**Action:** You must read and audit **EVERY** file in the `Job-alert-bot` directory (script, config, workflow, etc.).
**Checklist:**
- Check for **contradictions** between the script logic and the `config.yaml`.
- Ensure **NO hardcoded values** exist in `.py` files (must read from config).
- "Read, Compare, Think": Audit the entire system for architectural integrity.

## 3. POST-PUSH SERVER VERIFICATION
**Trigger:** Immediately after any `git push` returns success.
**Action:** You must verify that the code on the GitHub server matches your local state.
**Method:** Use `git fetch` and `git log origin/main -n 1` to confirm the commit hash.
**Rule:** Never assume success. Verify remote state explicitly.

## 4. STRATEGIC STANDARDS
- **Zero-Loss Strategy:** Prioritize individual iteration to avoid truncation/data loss.
- **Quota Safety:** Maintain the 3-session rotation to stay under 2,000 minutes.
- **100% Dynamic:** The script must remain a "Pure Engine" driven entirely by `config.yaml`.
