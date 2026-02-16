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
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-1000:], f, indent=4)

def send_email(subject, jobs, config):
    if not jobs: return False
    sender_email = config["email"]["sender_email"]
    sender_password = config["email"]["app_password"]
    recipient_email = config["email"]["recipient_email"]
    
    if "qwerty" in sender_password or not sender_password:
        print("!!! Email Error: App Password not found. Check GitHub Secrets.")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject
    html = f"<h3>{subject}</h3><ul>"
    for job in jobs:
        html += f"<li><b><a href='{job.get('job_url', '#')}'>{job.get('title')}</a></b> at {job.get('company')} ({job.get('location')})</li>"
    html += "</ul>"
    msg.attach(MIMEText(html, "html"))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print(f"--- SUCCESS: Email sent for {subject} ---")
        return True
    except Exception as e:
        print(f"!!! Email Error: {e}")
        return False

def run():
    config = load_config()
    history = load_history()
    seen_ids = {item["id"] for item in history}
    
    hours_to_check = config["search"].get("hours_old", 24)
    search_terms = config["search"]["search_terms"]
    india_locs = config["search"]["india_locations"]
    foreign_locs = config["search"]["foreign_locations"]
    
    # Using only major sites to speed up and avoid IP bans
    sites = ["linkedin", "indeed", "zip_recruiter"]
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting High-Speed Search for {len(search_terms)} optimized terms...")

    def fetch(terms, locations, is_india):
        found = []
        for loc in locations:
            for term in terms:
                print(f"  Searching: {term} in {loc}...", end="\r")
                try:
                    # Optimized Delay (Reduced to speed up while staying safe)
                    time.sleep(random.uniform(0.1, 0.5))
                    
                    res = scrape_jobs(
                        site_name=sites, 
                        search_term=term, 
                        location=loc, 
                        results_wanted=15, # Increased results to catch all OR variants
                        hours_old=hours_to_check,
                        country_indeed='india' if is_india else 'usa'
                    )
                    if res is not None and not res.empty:
                        new_results = res.to_dict('records')
                        for job in new_results:
                            # Unique ID based on Title, Company, and Location
                            jid = f"{job.get('title')}-{job.get('company')}-{job.get('location')}"
                            if jid not in seen_ids:
                                job['uid'] = jid
                                found.append(job)
                                seen_ids.add(jid)
                                print(f"\n    [FOUND] {job.get('title')} at {job.get('company')} ({loc})")
                except:
                    continue
        return found

    print("\n--- SEARCHING INDIA ---")
    new_india = fetch(search_terms, india_locs, True)
    
    print("\n--- SEARCHING INTERNATIONAL ---")
    new_foreign = fetch(search_terms, foreign_locs, False)

    print(f"\n--- Final Results: {len(new_india)} India, {len(new_foreign)} Global ---")

    if new_india: send_email(f"Job Alert: {len(new_india)} New Roles in India", new_india, config)
    if new_foreign: send_email(f"Job Alert: {len(new_foreign)} New International Roles", new_foreign, config)

    if new_india or new_foreign:
        for j in new_india + new_foreign:
            history.append({"id": j['uid'], "date": datetime.now().isoformat()})
        save_history(history)

if __name__ == "__main__":
    run()
