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
        json.dump(history[-1000:], f, indent=4)

def send_email(subject, jobs, config):
    if not jobs: return False
    sender_email = config["email"]["sender_email"]
    sender_password = os.environ.get("GMAIL_APP_PASSWORD") or config["email"].get("app_password")
    recipient_email = config["email"]["recipient_email"]
    if not sender_password or "qwerty" in sender_password: return False

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
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        return True
    except: return False

def run():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- OPTIMIZED STEALTH STARTING ---")
    config = load_config()
    history = load_history()
    seen_ids = {item["id"] for item in history}
    
    search_terms = config["search"]["search_terms"]
    india_locs = config["search"]["india_locations"]
    foreign_locs = config["search"]["foreign_locations"]
    sites = ["linkedin", "indeed", "glassdoor", "zip_recruiter"]
    
    def fetch(terms, locations, is_india):
        found = []
        for loc in locations:
            for term in terms:
                print(f"  > Searching: '{term}' in '{loc}'...")
                try:
                    # Healthy delay between searches to stay stealthy
                    time.sleep(random.uniform(4, 7))
                    
                    res = scrape_jobs(
                        site_name=sites, 
                        search_term=term, 
                        location=loc, 
                        results_wanted=15,
                        hours_old=config["search"].get("hours_old", 24),
                        country_indeed='india' if is_india else 'usa'
                    )
                    
                    if res is not None and not res.empty:
                        new_results = res.to_dict('records')
                        added = 0
                        for job in new_results:
                            jid = f"{job.get('title')}-{job.get('company')}-{job.get('location')}"
                            if jid not in seen_ids:
                                job['uid'] = jid
                                found.append(job)
                                seen_ids.add(jid)
                                added += 1
                                # print(f"    [FOUND] {job.get('title')} @ {job.get('company')}")
                        if added > 0: print(f"    [NEW] Found {added} new roles.")
                except Exception as e:
                    print(f"    [ERROR] Search failed for {term}: {str(e)[:50]}")
                    continue
        return found

    print("\n--- INDIA LOCATIONS ---")
    new_india = fetch(search_terms, india_locs, True)
    
    print("\n--- INTERNATIONAL LOCATIONS ---")
    new_foreign = fetch(search_terms, foreign_locs, False)

    total = len(new_india) + len(new_foreign)
    print(f"\n--- DONE. Found {total} New Jobs ---")

    if new_india: send_email(f"Job Alert: {len(new_india)} New Roles (India)", new_india, config)
    if new_foreign: send_email(f"Job Alert: {len(new_foreign)} New Roles (Intl)", new_foreign, config)

    if total > 0:
        for j in new_india + new_foreign:
            history.append({"id": j['uid'], "date": datetime.now().isoformat()})
        save_history(history)

if __name__ == "__main__":
    run()
