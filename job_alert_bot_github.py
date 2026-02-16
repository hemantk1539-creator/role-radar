import yaml
import json
import smtplib
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
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

def run():
    config = load_config()
    history = load_history()
    seen_ids = {item["id"] for item in history}
    
    search_terms = config["search"]["search_terms"]
    india_locs = config["search"]["india_locations"]
    foreign_locs = config["search"]["foreign_locations"]
    sites = ["linkedin", "indeed", "glassdoor", "zip_recruiter", "instahyre"]
    
    def fetch(terms, locations, is_india):
        found = []
        for term in terms:
            for loc in locations:
                try:
                    res = scrape_jobs(site_name=sites, search_term=term, location=loc, results_wanted=5, hours_old=1, country_indeed='india' if is_india else 'usa')
                    if res is not None and not res.empty:
                        for job in res.to_dict('records'):
                            jid = f"{job.get('title')}-{job.get('company')}-{job.get('location')}"
                            if jid not in seen_ids:
                                job['uid'] = jid
                                found.append(job)
                                seen_ids.add(jid)
                except: continue
        return found

    new_india = fetch(search_terms, india_locs, True)
    new_foreign = fetch(search_terms, foreign_locs, False)

    if new_india: send_email(f"GitHub Alert: New Jobs India", new_india, config)
    if new_foreign: send_email(f"GitHub Alert: New International Jobs", new_foreign, config)

    if new_india or new_foreign:
        for j in new_india + new_foreign:
            history.append({"id": j['uid'], "date": datetime.now().isoformat()})
        save_history(history)
        # In GitHub, we need to commit the updated history.json back to the repo.
        # This part is usually handled by a separate step in the YAML.

if __name__ == "__main__":
    run()
