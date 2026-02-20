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

# RATIONAL GLOBAL HUB GRID: 15 High-Signal Hubs
VALID_COUNTRIES = ['india', 'usa', 'uk', 'canada', 'australia', 'singapore', 'germany', 'ireland', 'netherlands', 'united arab emirates', 'poland', 'hong kong', 'qatar', 'malaysia', 'new zealand']
GLOBAL_OR_LOC = "USA OR UK OR Canada OR Australia OR Singapore OR Germany OR Ireland OR Netherlands OR United Arab Emirates OR Poland OR Hong Kong OR Qatar OR Malaysia OR New Zealand"
BLOCKED_SITES = ["glassdoor", "bayt", "zip_recruiter"] 

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

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-2000:], f, indent=4)

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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- GLOBAL HUB & REMOTE SEARCH STARTING ---")
    
    try:
        with open("heartbeat.txt", "w") as f:
            f.write(f"Last Run (UTC): {datetime.now().isoformat()}")
    except Exception as e:
        print(f"Heartbeat failed: {e}")

    config = load_config()
    history = load_history()
    seen_ids = {item["id"] for item in history}
    
    sender_password = os.environ.get("GMAIL_APP_PASSWORD") or config["email"].get("app_password")
    if not sender_password or "qwerty" in sender_password: 
        print(f"  [FATAL ERROR] GMAIL_APP_PASSWORD missing. Aborting run.")
        return False

    search_terms = config["search"]["search_terms"]
    locations = config["search"]["india_locations"]
    
    found_local = []
    found_remote = []

    for loc in locations:
        search_tasks = []
        if loc == "Remote":
            # 1. DEEP INDIA (Naukri, Indeed, LinkedIn)
            for site in ["naukri", "indeed", "linkedin"]:
                # RATIONAL FIX: LinkedIn "Remote" search from US IP needs "India" location to target correctly
                if site == "linkedin":
                    search_tasks.append({"site": site, "country": "india", "loc": "India"})
                else:
                    search_tasks.append({"site": site, "country": "india", "loc": loc})
            
            # 2. DEEP GLOBAL (Indeed) - Remaining 14 countries individually
            for c in [c for c in VALID_COUNTRIES if c != 'india']:
                search_tasks.append({"site": "indeed", "country": c, "loc": loc})
            
            # 3. WIDE GLOBAL (LinkedIn) - Grouped OR-logic (15 countries)
            search_tasks.append({"site": "linkedin", "country": "usa", "loc": GLOBAL_OR_LOC})
        else:
            # Local City Search (India Only)
            for site in ["linkedin", "indeed", "naukri"]:
                search_tasks.append({"site": site, "country": "india", "loc": loc})

        for task in search_tasks:
            for term in search_terms:
                site = task["site"]
                country_code = task["country"]
                search_loc = task["loc"]
                
                if site in BLOCKED_SITES: continue
                if site == "naukri" and country_code != "india": continue
                
                print(f"  > Searching: '{term[:50]}...' in '{search_loc}' on '{site}' via [{country_code}]...")
                try:
                    time.sleep(random.uniform(4, 6))
                    res = scrape_jobs(
                        site_name=[site], 
                        search_term=term, 
                        location=search_loc, 
                        results_wanted=config["search"].get("results_wanted", 40),
                        hours_old=config["search"].get("hours_old", 24),
                        country_indeed=country_code
                    )
                    
                    if res is not None and not res.empty:
                        new_results = res.to_dict('records')
                        for job in new_results:
                            title_str = str(job.get('title', '')).lower()
                            loc_str = str(job.get('location', '')).lower()
                            
                            # 1. MASTER WHITELIST (Seniority + Quality Domain)
                            levels = ["manager", "director", "head", "em", "staff", "engineering manager", "lead", "principal"]
                            domains = ["quality", "qe", "qa", "sdet", "set", "test", "testing", "automation"]
                            has_level = any(l in title_str for l in levels)
                            has_domain = any(d in title_str for d in domains)
                            
                            blacklist = ["junior", "jr", "associate", "trainee", "intern", "fresher", "marketing", "sales", "control", "us citizen", "green card", "authorized to work in the us", "us only", "north america only"]
                            is_blacklisted = any(b in title_str or b in loc_str for b in blacklist)

                            if not (has_level and has_domain) or is_blacklisted:
                                continue

                            # 2. GLOBAL SIGNAL CHECK (Fixed Net)
                            is_india_explicit = 'india' in loc_str or 'india' in title_str
                            
                            if loc == "Remote":
                                # RATIONAL FIX: If searching in India, we TRUST it's an India-Remote role.
                                if country_code == "india":
                                    pass 
                                else:
                                    # For Global Hubs (USA, UK, etc.), we keep a relaxed signal check 
                                    global_signals = ["anywhere", "global", "worldwide", "international", "apac", "asia", "emea", "distributed", "remote-first", "time zone", "overlap", "timezone", "remote-friendly"]
                                    has_signal = any(s in title_str or s in loc_str for s in global_signals)
                                    if not (has_signal or is_india_explicit):
                                        continue

                            # --- UNIQUE ID & CATEGORIZATION ---
                            jurl = job.get('job_url', '')
                            if not jurl: continue
                            
                            jid = hashlib.md5(jurl.encode('utf-8')).hexdigest()
                            if jid not in seen_ids:
                                job['uid'] = jid
                                seen_ids.add(jid)
                                
                                # Category Logic
                                if (loc == "Remote" or any(r in loc_str or r in title_str for r in ['remote', 'anywhere', 'global'])) or is_india_explicit:
                                    if 'remote' in loc_str or 'remote' in title_str or 'anywhere' in loc_str or loc == "Remote":
                                        found_remote.append(job)
                                    else:
                                        found_local.append(job)
                                else:
                                    found_local.append(job)
                except Exception as e:
                    print(f"    [SITE ERROR] '{site}' failed: {str(e)[:100]}")
                    continue

    total = len(found_local) + len(found_remote)
    print(f"\n--- DONE. Found {total} New Jobs ---")

    if found_local: send_email(f"Local Alert: {len(found_local)} New City Roles", found_local, config)
    if found_remote: send_email(f"Remote Alert: {len(found_remote)} New Global Remote Roles", found_remote, config)

    if total > 0:
        for j in found_local + found_remote:
            history.append({"id": j['uid'], "date": datetime.now().isoformat()})
        save_history(history)
    
    return True

if __name__ == "__main__":
    if not run():
        sys.exit(1)
