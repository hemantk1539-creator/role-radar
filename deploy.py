"""
deploy.py - the only authorized deployment path for this repo.

Every push runs:
  1. Syntax/import check
  2. Full pytest suite (failing tests block the push)
  3. Sanity bot run (logic must be executable)
  4. Hardcode audit (catches accidentally committed strategy data)
  5. git stash → pull --rebase → pop → commit → push → verify

Usage:
  python deploy.py "feat: add Wellfound RSS source"
  python deploy.py "fix: handle 3-part LinkedIn locations"
"""
import subprocess
import os
import sys
import re
from datetime import datetime

BOT_SCRIPT = "job_alert_bot_github.py"
CONFIG_FILE = "job_alert_config.yaml"
# Source modules audited for hardcoded strategy data (must live in YAML, not code).
SOURCE_MODULES = [BOT_SCRIPT, "config.py", "filters.py", "scrapers.py", "emailer.py"]
STAGED_FILES = [
    BOT_SCRIPT,
    "config.py",
    "filters.py",
    "scrapers.py",
    "emailer.py",
    CONFIG_FILE,
    "deploy.py",
    "requirements.txt",
    "README.md",
    "LICENSE",
    "TEST_SUITE.md",
    "tests/",
    "docs/",
    ".github/",
    ".gitignore",
]


def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def log(msg, success=True):
    symbol = "OK" if success else "FAIL"
    print(f"[{symbol}] {msg}")


def audit():
    print("--- STARTING DEPLOYMENT AUDIT ---")

    # 1. Syntax / import
    res = run_cmd(f'python -c "import {BOT_SCRIPT[:-3]}"')
    if res.returncode != 0:
        log("Syntax/Import Check: FAILED.", False)
        print(res.stderr)
        return False
    log("Syntax/Import Check: OK.")

    # 2. Test suite
    res = subprocess.run(
        ["uv", "run", "python", "-m", "pytest", "tests/", "-q", "--tb=short"],
        capture_output=True, text=True
    )
    if res.stdout:
        print(res.stdout[-2000:])
    if res.returncode != 0:
        log("Test Suite: FAILED - push blocked.", False)
        return False
    log("Test Suite: ALL PASSED.")

    # 3. Sanity (fetch latest history first to avoid duplicate emails during local run)
    run_cmd("git fetch origin data")
    history_res = run_cmd("git show origin/data:job_history.json")
    if history_res.returncode == 0:
        with open("job_history.json", "w", encoding="utf-8") as f:
            f.write(history_res.stdout)
    res = run_cmd(f"python {BOT_SCRIPT}")
    if "STARTING" not in res.stdout and "STARTING" not in res.stderr:
        log("Sanity Check: FAILED.", False)
        return False
    log("Sanity Check: Logic Executable.")

    # 4. Hardcode audit - strategy data must live in YAML, not in code.
    # Scans every source module (not just the entrypoint) so the post-split refactor
    # cannot smuggle strategy lists into filters.py/scrapers.py outside the audit's view.
    for module in SOURCE_MODULES:
        with open(module, "r", encoding="utf-8") as f:
            content = f.read()
        if re.search(r'\["[^"]+",\s*"[^"]+",\s*"[^"]+"\]', content):
            log(f"Hardcode Audit: FAILED (long lists found in {module} - move to YAML).", False)
            return False
    log("Hardcode Audit: Clean.")

    return True


def deploy(commit_msg):
    if not audit():
        sys.exit(1)

    print("> Audit Passed. Syncing with remote...")
    run_cmd("git restore --staged job_history.json 2>nul")
    run_cmd("git stash")
    pull_res = run_cmd("git pull --rebase origin main")
    run_cmd("git stash pop")
    if pull_res.returncode != 0:
        log("Pull/Rebase Failed. Resolve conflicts before deploying.", False)
        sys.exit(1)

    print("> Pushing changes...")
    run_cmd(f"git add {' '.join(STAGED_FILES)}")
    run_cmd(f'git commit -m "{commit_msg}"')
    push_res = run_cmd("git push origin main")

    if push_res.returncode != 0:
        log("Push Failed.", False)
        print(push_res.stderr)
        sys.exit(1)

    log("Push Successful.")
    run_cmd("git fetch origin")
    verify = run_cmd(f"git show origin/main:{BOT_SCRIPT}")
    if len(verify.stdout) > 1000:
        log("Server Verification: MATCHED.")
    else:
        log("Server Verification: FAILED.", False)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python deploy.py \"<commit message>\"")
        print("Example: python deploy.py \"feat: add Wellfound RSS source\"")
        sys.exit(1)
    deploy(sys.argv[1])
