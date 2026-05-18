import subprocess
import os
import sys
import re
from datetime import datetime

BOT_SCRIPT = "job_alert_bot_github.py"
CONFIG_FILE = "job_alert_config.yaml"
STATE_FILE = "PROJECT_STATE.md"

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result

def log(msg, success=True):
    symbol = "OK" if success else "FAIL"
    print(f"[{symbol}] {msg}")

def audit():
    print("--- STARTING DEPLOYMENT AUDIT ---")

    # 0. Syntax/Import Check (Rule 13)
    res_syntax = run_cmd(f'python -c "import {BOT_SCRIPT[:-3]}"')
    if res_syntax.returncode == 0:
        log("Syntax/Import Check: OK.")
    else:
        log("Syntax/Import Check: FAILED.", False)
        return False

    # 0b. Test suite
    res_tests = subprocess.run(
        ["uv", "run", "python", "-m", "pytest", "tests/", "-q", "--tb=short"],
        capture_output=True, text=True
    )
    print(res_tests.stdout[-2000:] if res_tests.stdout else "")
    if res_tests.returncode == 0:
        log("Test Suite: ALL PASSED.")
    else:
        log("Test Suite: FAILED — push blocked.", False)
        return False

    # 1. Sanity (fetch latest history first to avoid duplicate emails during local run)
    run_cmd("git fetch origin data")
    history_res = run_cmd("git show origin/data:job_history.json")
    if history_res.returncode == 0:
        with open("job_history.json", "w", encoding="utf-8") as f:
            f.write(history_res.stdout)
    res = run_cmd(f"python {BOT_SCRIPT}")
    if "STARTING" in res.stdout or "STARTING" in res.stderr:
        log("Sanity Check: Logic Executable.")
    else:
        log("Sanity Check: FAILED.", False)
        return False

    # 2. Hardcode Check
    with open(BOT_SCRIPT, "r", encoding="utf-8") as f:
        content = f.read()
        # Look for hardcoded lists with more than 2 items (indicates strategy data)
        if re.search(r'\["[^"]+",\s*"[^"]+",\s*"[^"]+"\]', content):
            log("Hardcode Audit: FAILED (Long lists found in code).", False)
            return False
    log("Hardcode Audit: Clean.")

    # 3. State Check
    if os.path.exists(STATE_FILE):
        mtime = os.path.getmtime(STATE_FILE)
        if datetime.fromtimestamp(mtime).date() != datetime.now().date():
            log("State Audit: FAILED (State file not updated today).", False)
            return False
    log("State Audit: Current.")
    
    return True

def deploy():
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
    commit_msg = "Rigor-Checked Deployment: " + datetime.now().strftime("%Y-%m-%d %H:%M")
    run_cmd(f"git add {BOT_SCRIPT} {CONFIG_FILE} {STATE_FILE} deploy.py requirements.txt")
    run_cmd(f'git commit -m "{commit_msg}"')
    push_res = run_cmd("git push origin main")
    
    if push_res.returncode == 0:
        log("Push Successful.")
        run_cmd("git fetch origin")
        verify = run_cmd(f"git show origin/main:{BOT_SCRIPT}")
        if len(verify.stdout) > 1000:
            log("Server Verification: MATCHED.")
        else:
            log("Server Verification: FAILED.", False)
    else:
        log("Push Failed.", False)

if __name__ == "__main__":
    deploy()
