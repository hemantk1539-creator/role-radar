import yaml
import json
import smtplib
import time
import random
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import sys

try:
    from jobspy import scrape_jobs
except ImportError:
    print("Error: 'python-jobspy' is not installed.")
    sys.exit(1)

CONFIG_FILE = "job_alert_config.yaml"
HISTORY_FILE = "job_history.json"

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except: return []
    return []

def save_history(history, config):
    max_h = config["search"].get("max_history", 2000)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-max_h:], f, indent=4)

def send_email(subject, jobs, config):
    if not jobs: return False
    sender_email = config["email"]["sender_email"]
    sender_password = os.environ.get("GMAIL_APP_PASSWORD") or config["email"].get("app_password")
    recipient_email = config["email"]["recipient_email"]
    if not sender_password or "qwerty" in sender_password: 
        print(f"  [SKIP] Skipping email: Credentials missing.")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject
    
    loc_counts = {}
    for j in jobs:
        l = j.get('location', 'Unknown')
        loc_counts[l] = loc_counts.get(l, 0) + 1
    
    summary_html = "<ul>"
    for loc, count in sorted(loc_counts.items()):
        summary_html += f"<li><b>{loc}:</b> {count} jobs</li>"
    summary_html += "</ul>"

    html = f"<h3>{subject}</h3>"
    html += f"<p><b>Total Found:</b> {len(jobs)}</p>"
    html += "<h4>Breakdown by Location:</h4>"
    html += summary_html
    html += "<hr><table border='1' style='border-collapse: collapse; width: 100%;'>"
    html += "<tr style='background-color: #eee;'><th>Title</th><th>Company</th><th>Location</th><th>Site</th><th>Link</th></tr>"
    for job in jobs:
        html += f"<tr><td>{job.get('title')}</td><td>{job.get('company')}</td><td>{job.get('location')}</td><td>{job.get('site')}</td><td><a href='{job.get('job_url')}'>Apply</a></td></tr>"
    html += "</table>"
    msg.attach(MIMEText(html, "html"))

    try:
        print(f"  [MAIL] Connecting to SMTP for '{subject}'...")
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print(f"  [SUCCESS] Email sent.")
        return True
    except Exception as e:
        print(f"  [ERROR] Email failed: {str(e)[:100]}")
        return False

def run():
    config = load_config()
    
    # DYNAMIC MODE DETECTION
    now_hour = datetime.now().hour
    velocity_window = config["search"].get("velocity_window", [19, 20, 21, 22])
    is_velocity = (now_hour in velocity_window)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- DYNAMIC ENGINE (Mode: {'Velocity' if is_velocity else 'Deep'}) STARTING ---")
    
    try:
        with open("heartbeat.txt", "w") as f:
            f.write(f"Last Run (UTC): {datetime.now().isoformat()}")
    except Exception as e:
        print(f"Heartbeat failed: {e}")

    history = load_history()
    seen_ids = {item["id"] for item in history}
    
    sender_password = os.environ.get("GMAIL_APP_PASSWORD") or config["email"].get("app_password")
    if not sender_password or "qwerty" in sender_password: 
        print(f"  [FATAL ERROR] GMAIL_APP_PASSWORD missing. Aborting run.")
        return False

    # LOAD ALL DATA FROM CONFIG
    search_terms = config["search"]["search_terms"]
    india_locations = config["search"]["india_locations"]
    global_hubs = config["search"]["global_hubs"]
    blacklist = [b.lower() for b in config["search"]["blacklist"]]
    levels = [l.lower() for l in config["search"]["levels"]]
    domains = [d.lower() for d in config["search"]["domains"]]
    blocked_sites = config["search"].get("blocked_sites", [])
    india_code = config["search"].get("india_country_code", "india")
    global_loc = config["search"].get("global_search_loc", "Remote")
    remote_signals = config["search"].get("remote_signals", ["remote"])
    
    found_local = []
    found_india_remote = []
    found_global_remote = []

    all_tasks = []
    
    # 1. INDIA CITIES (Mandate 1 & 2)
    for loc in india_locations:
        all_tasks.append({"site": "linkedin", "country": india_code, "loc": loc})
        if not is_velocity:
            all_tasks.append({"site": "naukri", "country": india_code, "loc": loc})
            all_tasks.append({"site": "indeed", "country": india_code, "loc": loc})
            
    # 2. GLOBAL HUB GRID (Mandate 3)
    for country in global_hubs:
        all_tasks.append({"site": "linkedin", "country": country, "loc": global_loc})
        if not is_velocity:
            all_tasks.append({"site": "indeed", "country": country, "loc": global_loc})

    for task in all_tasks:
        for term in search_terms:
            site = task["site"]
            country_code = task["country"]
            search_loc = task["loc"]
            
            if site in blocked_sites: continue
            
            print(f"  > Searching: '{term[:40]}...' in '{search_loc}' [{country_code}] via {site}...")
            try:
                time.sleep(random.uniform(4, 6))
                res = scrape_jobs(
                    site_name=[site], 
                    search_term=term, 
                    location=search_loc, 
                    results_wanted=config["search"].get("results_wanted", 30),
                    hours_old=config["search"].get("hours_old", 24),
                    country_indeed=country_code
                )
                
                if res is not None and not res.empty:
                    new_results = res.to_dict('records')
                    for job in new_results:
                        title_str = str(job.get('title', '')).lower()
                        loc_str = str(job.get('location', '')).lower()
                        
                        # A. HUB-APPLICABILITY GUARD
                        if any(b in title_str or b in loc_str for b in blacklist):
                            continue

                        # B. SENIORITY WHITELIST
                        has_level = any(l in title_str for l in levels)
                        has_domain = any(d in title_str for d in domains)
                        if not (has_level and has_domain):
                            continue

                        # C. ID & CATEGORIZATION
                        jurl = job.get('job_url', '')
                        if not jurl: continue
                        
                        jid = hashlib.md5(jurl.encode('utf-8')).hexdigest()
                        if jid not in seen_ids:
                            job['uid'] = jid
                            seen_ids.add(jid)
                            
                            # --- 3-BUCKET CATEGORIZATION (Rigor + Separation) ---
                            # Note: Reading Title/Location Header (not full JD)
                            is_remote_explicit = any(r in loc_str or r in title_str for r in remote_signals)
                            is_local_city = any(city.lower() in loc_str for city in india_locations if city != "Remote" and city != global_loc)
                            
                            if is_remote_explicit:
                                if country_code == india_code:
                                    found_india_remote.append(job)
                                else:
                                    found_global_remote.append(job)
                            elif is_local_city:
                                found_local.append(job)
                            elif country_code != india_code:
                                # Global Hub leak (e.g. US local job with no Remote tag) -> REJECT
                                continue
                            else:
                                # India local job with no specific city match or remote tag -> Local Fallback
                                found_local.append(job)
                
                time.sleep(1) # Cooldown between terms
            except Exception as e:
                print(f"    [SITE ERROR] '{site}' failed: {str(e)[:100]}")
                continue

    total = len(found_local) + len(found_india_remote) + len(found_global_remote)
    print(f"\n--- DONE. Found {total} New Jobs ---")

    if found_local: send_email(f"Local Alert: {len(found_local)} New City Roles", found_local, config)
    if found_india_remote: send_email(f"India Remote Alert: {len(found_india_remote)} New Remote Roles", found_india_remote, config)
    if found_global_remote: send_email(f"Global Remote Alert: {len(found_global_remote)} New Global Remote Roles", found_global_remote, config)

    if total > 0:
        for j in found_local + found_india_remote + found_global_remote:
            history.append({"id": j['uid'], "date": datetime.now().isoformat()})
        save_history(history, config)
    
    return True

if __name__ == "__main__":
    if not run():
        sys.exit(1)
