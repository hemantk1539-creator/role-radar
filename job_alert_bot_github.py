import yaml
import json
import smtplib
import time
import random
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
    
    html = f"<h3>{subject}</h3><table border='1' style='border-collapse: collapse; width: 100%;'>"
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- 4X DAILY ZERO-MISS SEARCH STARTING ---")
    config = load_config()
    history = load_history()
    seen_ids = {item["id"] for item in history}
    
    search_terms = config["search"]["search_terms"]
    locations = config["search"]["india_locations"]
    
    site_batches = [
        ["linkedin", "indeed"], 
        ["glassdoor"],           
        ["zip_recruiter"]        
    ]
    
    found_local = []
    found_remote = []

    for loc in locations:
        for term in search_terms:
            for sites in site_batches:
                print(f"  > Searching: '{term}' in '{loc}' on {sites}...")
                try:
                    # Optimized stealth delay for 4x daily frequency
                    time.sleep(random.uniform(4, 6))
                    res = scrape_jobs(
                        site_name=sites, 
                        search_term=term, 
                        location=loc, 
                        results_wanted=config["search"].get("results_wanted", 15),
                        hours_old=config["search"].get("hours_old", 24),
                        country_indeed='india'
                    )
                    
                    if res is not None and not res.empty:
                        new_results = res.to_dict('records')
                        for job in new_results:
                            title_str = str(job.get('title', '')).lower()
                            
                            # --- STRICT EXECUTIVE FILTER ---
                            levels = ["manager", "director", "head", "vp", "em", "staff", "engineering manager"]
                            domains = ["quality engineering", "quality assurance", "qe", "qa", "sdet", "set", "test", "testing"]
                            has_level = any(l in title_str for l in levels)
                            has_domain = any(d in title_str for d in domains)
                            blacklist = ["junior", "jr", "associate", "trainee", "intern", "fresher", "control", "marketing", "sales", "business development"]
                            is_blacklisted = any(b in title_str for b in blacklist)

                            if not (has_level and has_domain) or is_blacklisted:
                                continue

                            jurl = job.get('job_url', '')
                            if not jurl: continue
                            
                            jid = str(hash(jurl))
                            if jid not in seen_ids:
                                job['uid'] = jid
                                seen_ids.add(jid)
                                
                                loc_str = str(job.get('location', '')).lower()
                                if 'remote' in loc_str or 'remote' in title_str or 'anywhere' in loc_str or loc == 'Remote':
                                    found_remote.append(job)
                                else:
                                    found_local.append(job)
                except Exception as e:
                    print(f"    [SITE ERROR] {sites} failed: {str(e)[:50]}")
                    continue

    total = len(found_local) + len(found_remote)
    print(f"\n--- DONE. Found {total} New Jobs ---")

    if found_local: send_email(f"Local Alert: {len(found_local)} New City Roles", found_local, config)
    if found_remote: send_email(f"Remote Alert: {len(found_remote)} New Remote Roles", found_remote, config)

    if total > 0:
        for j in found_local + found_remote:
            history.append({"id": j['uid'], "date": datetime.now().isoformat()})
        save_history(history)

if __name__ == "__main__":
    run()
