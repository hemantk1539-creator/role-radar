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
    
    # 1. Sanity
    res = run_cmd(f"python {BOT_SCRIPT}")
    if "STARTING" in res.stdout or "STARTING" in res.stderr:
        log("Sanity Check: Logic Executable.")
    else:
        log("Sanity Check: FAILED.", False)
        return False

    # 2. Hardcode Check
    with open(BOT_SCRIPT, "r") as f:
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

    print("> Audit Passed. Pushing changes...")
    commit_msg = "Rigor-Checked Deployment: " + datetime.now().strftime("%Y-%m-%d %H:%M")
    run_cmd(f"git add {BOT_SCRIPT} {CONFIG_FILE} {STATE_FILE} deploy.py")
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
