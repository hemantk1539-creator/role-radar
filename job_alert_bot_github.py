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

# Try to import jobspy, fail gracefully if missing
try:
    from jobspy import scrape_jobs
except ImportError:
    print("Error: 'python-jobspy' is not installed.")
    sys.exit(1)

CONFIG_FILE = "job_alert_config.yaml"
HISTORY_FILE = "job_history.json"

def load_config():
    """Load the YAML configuration file."""
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

def load_history():
    """Load the job history JSON file."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not read history file ({e}). Starting fresh.")
            return []
    return []

def save_history(history):
    """Save the job history to JSON, keeping only the last 1000 entries."""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-1000:], f, indent=4)

def send_email(subject, jobs, config):
    """Send an email with the list of found jobs."""
    if not jobs: return False
    
    sender_email = config["email"]["sender_email"]
    # Securely get password from Environment Variable (GitHub Secrets) first
    sender_password = os.environ.get("GMAIL_APP_PASSWORD") or config["email"].get("app_password")
    recipient_email = config["email"]["recipient_email"]
    
    if not sender_password or "qwerty" in sender_password or "YOUR_APP_PASSWORD" in sender_password:
        print(f"!!! Email Error: App Password not configured. Set GMAIL_APP_PASSWORD in GitHub Secrets.")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = subject
    
    # Build HTML Table
    html = f"<h3>{subject}</h3><p>Run Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
    html += "<table border='1' cellpadding='5' style='border-collapse: collapse; width: 100%;'>"
    html += "<tr style='background-color: #f2f2f2;'><th>Title</th><th>Company</th><th>Location</th><th>Site</th><th>Link</th></tr>"
    
    for job in jobs:
        title = job.get('title', 'N/A')
        company = job.get('company', 'N/A')
        location = job.get('location', 'N/A')
        site = job.get('site', 'N/A')
        url = job.get('job_url', '#')
        
        html += f"<tr><td>{title}</td><td>{company}</td><td>{location}</td><td>{site}</td><td><a href='{url}'>Apply</a></td></tr>"
    
    html += "</table>"
    msg.attach(MIMEText(html, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print(f"--- SUCCESS: Email sent to {recipient_email} with {len(jobs)} jobs ---")
        return True
    except Exception as e:
        print(f"!!! Email Error: {e}")
        return False

def run():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- JOB BOT STARTING ---")
    
    config = load_config()
    history = load_history()
    seen_ids = {item["id"] for item in history}
    
    hours_to_check = config["search"].get("hours_old", 24)
    search_terms = config["search"]["search_terms"]
    india_locs = config["search"]["india_locations"]
    foreign_locs = config["search"]["foreign_locations"]
    
    # Removed 'indeed' for now if it causes issues, or keep it but handle errors
    sites = ["linkedin", "glassdoor", "zip_recruiter", "indeed"]
    
    # Randomize user agent offset slightly to appear more human
    time.sleep(random.uniform(1, 3))

    def fetch(terms, locations, is_india):
        found = []
        for loc in locations:
            for term in terms:
                print(f"  > Searching: '{term}' in '{loc}'...")
                try:
                    # Random delay between requests is CRITICAL to avoid blocks
                    delay = random.uniform(3, 8) 
                    time.sleep(delay)
                    
                    # Fetch more results (40) to filter locally
                    res = scrape_jobs(
                        site_name=sites, 
                        search_term=term, 
                        location=loc, 
                        results_wanted=40, 
                        hours_old=hours_to_check,
                        country_indeed='india' if is_india else 'usa'
                    )
                    
                    if res is not None and not res.empty:
                        print(f"    - Found {len(res)} raw results. Filtering...")
                        new_results = res.to_dict('records')
                        added_count = 0
                        for job in new_results:
                            # Create a unique ID
                            jid = f"{job.get('title')}-{job.get('company')}-{job.get('location')}"
                            
                            # Deduplicate against history AND current run
                            if jid not in seen_ids:
                                job['uid'] = jid
                                found.append(job)
                                seen_ids.add(jid)
                                added_count += 1
                                # print(f"      + New: {job.get('title')} ({job.get('company')})")
                        print(f"    - Added {added_count} new unique jobs.")
                    else:
                        print(f"    - No results found (or blocked).")
                        
                except Exception as e:
                    print(f"    [ERROR] Failed searching {term} in {loc}: {str(e)[:100]}")
                    continue
        return found

    print("\n--- SEARCHING INDIA LOCATIONS ---")
    new_india = fetch(search_terms, india_locs, True)
    
    print("\n--- SEARCHING INTERNATIONAL LOCATIONS ---")
    new_foreign = fetch(search_terms, foreign_locs, False)

    total_found = len(new_india) + len(new_foreign)
    print(f"\n--- DONE. Total New Jobs: {total_found} ({len(new_india)} India, {len(new_foreign)} Global) ---")

    if new_india: 
        send_email(f"Job Alert: {len(new_india)} New Roles (India)", new_india, config)
    if new_foreign: 
        send_email(f"Job Alert: {len(new_foreign)} New Roles (International)", new_foreign, config)

    # Save history if we found anything
    if total_found > 0:
        for j in new_india + new_foreign:
            history.append({"id": j['uid'], "date": datetime.now().isoformat()})
        save_history(history)
    else:
        print("No new jobs to save.")

if __name__ == "__main__":
    run()
