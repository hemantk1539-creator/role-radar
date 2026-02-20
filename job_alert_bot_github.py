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
    # AUTOMATIC MODE DETECTION (Based on cron-job.org windows)
    # 06:41 UTC (12:11 PM IST) -> Deep
    # 12:41 UTC (06:11 PM IST) -> Deep
    # 19:41 UTC (01:11 AM IST) -> Velocity (LinkedIn Only)
    now_hour = datetime.now().hour
    # Trigger Velocity mode for the 01:11 AM IST window (19:00 - 22:00 UTC)
    is_velocity = (19 <= now_hour <= 22)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- DATA-PROVEN MASTERPIECE STARTING (Mode: {'Velocity' if is_velocity else 'Deep'}) ---")
    
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
    # HIGH-PRECISION CITY LIST (Mandate 1 & 2)
    india_locations = ["Bengaluru", "Pune", "Mumbai", "Hyderabad", "Delhi", "Gurugram", "Noida", "Remote"]
    
    found_local = []
    found_remote = []

    all_tasks = []
    
    # 1. INDIA CITIES (Mandate 1 & 2)
    for loc in india_locations:
        all_tasks.append({"site": "linkedin", "country": "india", "loc": loc})
        if not is_velocity:
            all_tasks.append({"site": "naukri", "country": "india", "loc": loc})
            all_tasks.append({"site": "indeed", "country": "india", "loc": loc})
            
    # 2. GLOBAL HUB GRID (Mandate 3)
    for country in [c for c in VALID_COUNTRIES if c != 'india']:
        all_tasks.append({"site": "linkedin", "country": country, "loc": "Remote"})
        if not is_velocity:
            all_tasks.append({"site": "indeed", "country": country, "loc": "Remote"})

    for task in all_tasks:
        for term in search_terms:
            site = task["site"]
            country_code = task["country"]
            search_loc = task["loc"]
            
            if site in BLOCKED_SITES: continue
            
            print(f"  > Searching: '{term[:40]}...' in '{search_loc}' [{country_code}] via {site}...")
            try:
                time.sleep(random.uniform(4, 6)) # Stealth delay
                res = scrape_jobs(
                    site_name=[site], 
                    search_term=term, 
                    location=search_loc, 
                    results_wanted=30,
                    hours_old=24,
                    country_indeed=country_code
                )
                
                if res is not None and not res.empty:
                    new_results = res.to_dict('records')
                    for job in new_results:
                        title_str = str(job.get('title', '')).lower()
                        loc_str = str(job.get('location', '')).lower()
                        
                        # A. EXHAUSTIVE UNIVERSAL HUB-APPLICABILITY GUARD
                        blacklist = [
                            "us citizen", "green card", "authorized to work in the us", "us only", "north america only", "canadian citizen", "canadian pr",
                            "uk resident", "eu citizen", "right to work in the uk", "british citizen", "eu resident", "eu work permit", "german resident", "blue card holder",
                            "australian citizen", "nz resident", "australian resident", "permanent resident", "singaporean only", "sc/pr", "hk permanent resident", "hkid holder", "malaysian only", "malaysian citizen",
                            "emirati national", "emirati only", "gcc national", "qatari national", "local hire only", "in-country hire", "visa transfer",
                            "visa sponsorship not available", "no sponsorship", "citizen only", "work authorization required", "residency required", "relocation required",
                            "junior", "jr", "associate", "trainee", "intern", "fresher", "marketing", "sales"
                        ]
                        blacklisted_word = next((b for b in blacklist if b in title_str or b in loc_str), None)
                        if blacklisted_word:
                            continue

                        # B. SENIORITY WHITELIST (Aligned with 10.5+ Year Profile)
                        levels = ["manager", "director", "head", "em", "staff", "engineering manager", "lead", "principal", "architect"]
                        domains = ["quality", "qe", "qa", "sdet", "set", "test", "testing", "automation"]
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
                            
                            is_remote_signal = any(r in loc_str or r in title_str for r in ['remote', 'anywhere', 'global'])
                            is_local_city = any(city.lower() in loc_str for city in ["bengaluru", "pune", "mumbai", "hyderabad", "delhi", "gurgaon", "noida", "gurugram"])
                            
                            if search_loc == "Remote" or is_remote_signal:
                                found_remote.append(job)
                            elif is_local_city:
                                found_local.append(job)
                            elif country_code == "india":
                                found_remote.append(job)
                            else:
                                found_remote.append(job)
                
                time.sleep(1) # Term Cooldown
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
