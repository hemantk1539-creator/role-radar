import yaml
import re
import json
import requests
import feedparser
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
    from jobspy.model import Country
except ImportError:
    print("Error: 'python-jobspy' is not installed.")
    sys.exit(1)

# MONKEY-PATCH: Prevent JobSpy from crashing on unknown international countries
# LinkedIn sometimes returns 3-part locations (e.g. "City, State, Country") for countries 
# not in JobSpy's whitelist. This patch ensures the search continues.
_original_from_string = Country.from_string
def patched_from_string(cls, country_str: str):
    try:
        return _original_from_string(country_str)
    except ValueError:
        return Country.WORLDWIDE
Country.from_string = classmethod(patched_from_string)

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

def fetch_global_intelligence(config, levels, domains):
    """
    POWER 6 HUB: The Centralized Global Remote Intelligence Layer.
    Fetches and snipes jobs from 20+ specialized platforms via 6 Master Hubs.
    """
    print("\n--- GLOBAL INTELLIGENCE: FETCHING FROM POWER 6 HUBS ---")
    jobs = []
    
    def is_match(title):
        t = title.lower()
        has_level = any(re.search(r'\b' + re.escape(l) + r'\b', t, re.IGNORECASE) for l in levels)
        has_domain = any(re.search(r'\b' + re.escape(d) + r'\b', t, re.IGNORECASE) for d in domains)
        return has_level and has_domain

    # HUB 1: The Universe (Himalayas + Remotive)
    for source, url in [("Himalayas", config["search"].get("himalayas_api")), ("Remotive", config["search"].get("remotive_api"))]:
        if not url: continue
        try:
            print(f"  > [Hub 1] Polling {source} API...")
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for j in data.get("jobs", []):
                    title = j.get("title", "")
                    if is_match(title):
                        jobs.append({
                            "title": title,
                            "company": j.get("companyName") or j.get("company_name") or j.get("company"),
                            "location": f"Remote [Signal: {source}]",
                            "job_url": j.get("applicationLink") or j.get("url") or j.get("application_url"),
                            "site": source.lower(),
                            "date": j.get("pubDate") or j.get("published_at", "")
                        })
        except Exception as e: print(f"    [{source} ERROR]: {e}")

    # HUB 2 & 4 & 5: RSS Specialty (YC, Wellfound, WWR, JS-Remotely, Arc.dev, Otta)
    feeds = [
        ("WWR", config["search"].get("wwr_feed")),
        ("JS-Remotely", config["search"].get("js_remotely_feed")),
        ("Arc.dev", config["search"].get("arc_dev_feed")),
        ("Wellfound", config["search"].get("wellfound_feed")),
        ("YC", config["search"].get("yc_api")),
        ("Remotive", config["search"].get("remotive_api")) # Remotive also has an RSS fallback
    ]
    for source, url in feeds:
        if not url: continue
        try:
            print(f"  > [Hub 2/4/5] Polling {source} RSS/API...")
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                if is_match(title):
                    jobs.append({
                        "title": title,
                        "company": entry.get("author") or source,
                        "location": f"Remote [Signal: {source}]",
                        "job_url": entry.get("link"),
                        "site": source.lower(),
                        "date": entry.get("published", "")
                    })
        except Exception as e: print(f"    [{source} ERROR]: {e}")

    # HUB 3: Legal Safety (Deel & Remote.com)
    # These platforms are highly protective; we hit their public job-listing APIs
    for source, url in [("Remote.com", config["search"].get("remote_com_api")), ("Deel", config["search"].get("deel_api"))]:
        if not url: continue
        try:
            print(f"  > [Hub 3] Polling {source} API...")
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                # Standardized processing for EOR boards
                for j in res.json().get("jobs", []):
                    title = j.get("title", "")
                    if is_match(title):
                        jobs.append({"title": title, "company": j.get("company", source), "location": f"Remote [Signal: {source}]", "job_url": j.get("url"), "site": source.lower(), "date": j.get("created_at", "")})
        except: continue

    # HUB 6: The Elite ATS Crawler (Direct-to-Source)
    ats_atlas = config["search"].get("ats_atlas", {})
    
    # Greenhouse
    for token in ats_atlas.get("greenhouse", []):
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                for j in res.json().get("jobs", []):
                    title = j.get("title", "")
                    if is_match(title):
                        jobs.append({"title": title, "company": token.capitalize(), "location": f"Remote [Signal: ATS-{token}]", "job_url": j.get("absolute_url"), "site": f"ats-{token}", "date": j.get("updated_at", "")})
        except: continue

    # Lever
    for token in ats_atlas.get("lever", []):
        try:
            url = f"https://api.lever.co/v0/postings/{token}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                for j in res.json():
                    title = j.get("text", "")
                    if is_match(title):
                        jobs.append({"title": title, "company": token.capitalize(), "location": f"Remote [Signal: ATS-{token}]", "job_url": j.get("hostedUrl"), "site": f"ats-{token}", "date": j.get("createdAt", "")})
        except: continue

    # Ashby / Breezy / Pinpoint (Direct JSON Endpoints)
    for ats_type, atlas_key in [("ashby", "ashby"), ("breezy", "breezy"), ("pinpoint", "pinpoint")]:
        for token in ats_atlas.get(atlas_key, []):
            try:
                url = f"https://api.ashbyhq.com/posting-api/job-board/{token}" if ats_type == "ashby" else \
                      f"https://{token}.breezy.hr/json" if ats_type == "breezy" else \
                      f"https://{token}.pinpointvis.com/api/v1/jobs"
                res = requests.get(url, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    # Unified parsing for these modern ATS types
                    job_list = data.get("jobs", []) if ats_type != "ashby" else data.get("jobs", [])
                    for j in job_list:
                        title = j.get("title") or j.get("name") or j.get("text")
                        if is_match(title):
                            url_key = "job_url" if ats_type == "ashby" else "url" if ats_type == "breezy" else "absolute_url"
                            jobs.append({"title": title, "company": token.capitalize(), "location": f"Remote [Signal: ATS-{token}]", "job_url": j.get(url_key), "site": f"ats-{token}"})
            except: continue

    print(f"--- POWER 6 COMPLETE. Found {len(jobs)} Pre-Sniper Roles ---\n")
    return jobs

def send_email(subject, jobs, config, sniped_jobs=None):
    if not jobs and not sniped_jobs: return False
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
    html += "<hr><table border='1' cellpadding='5' style='border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;'>"
    html += "<tr style='background-color: #f2f2f2;'><th>Title</th><th>Company</th><th>Location (Signal)</th><th>Site</th><th>Link</th></tr>"
    for job in jobs:
        html += f"<tr><td>{job.get('title')}</td><td>{job.get('company')}</td><td>{job.get('location')}</td><td>{job.get('site')}</td><td><a href='{job.get('job_url')}'>Apply</a></td></tr>"
    html += "</table>"
    
    if sniped_jobs:
        html += "<br><hr><h3 style='color: #d9534f;'>FILTERED OUT (Review):</h3>"
        html += "<p>The following jobs matched the search but were blocked by your Blacklist/Seniority settings:</p>"
        html += "<table border='1' cellpadding='5' style='border-collapse: collapse; width: 100%; color: #777; font-size: 0.9em;'>"
        html += "<tr style='background-color: #ffe6e6;'><th>Reason</th><th>Title</th><th>Company</th><th>Location</th></tr>"
        for j in sniped_jobs:
            html += f"<tr><td><b>{j.get('sniped_reason')}</b></td><td>{j.get('title')}</td><td>{j.get('company')}</td><td>{j.get('location')}</td></tr>"
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- DEEP ENGINE STARTING ---")
    
    try:
        with open("heartbeat.txt", "w") as f:
            f.write(f"Last Run (UTC): {datetime.now().isoformat()}")
    except Exception as e:
        print(f"Heartbeat failed: {e}")

    history = load_history()
    seen_ids = {item["id"] for item in history}
    # Duplicate Sniper (Rule 9): Track fingerprint (Title + Company)
    seen_fingerprints = {item.get("fingerprint") for item in history if item.get("fingerprint")}
    
    sender_password = os.environ.get("GMAIL_APP_PASSWORD") or config["email"].get("app_password")
    if not sender_password or "qwerty" in sender_password: 
        print(f"  [FATAL ERROR] GMAIL_APP_PASSWORD missing. Aborting run.")
        return False

    # LOAD ALL DATA FROM CONFIG
    search_terms = config["search"]["search_terms"]
    india_search_cities = config["search"].get("india_search_cities", [])
    india_city_aliases = [c.lower() for c in config["search"].get("india_city_aliases", [])]
    global_hubs = config["search"]["global_hubs"]
    blacklist = [b.lower() for b in config["search"]["blacklist"]]
    # JD Sniper Terms (Rule 9)
    residency_signals = [r.lower() for r in config["search"].get("residency_signals", [])]
    
    levels = [l.lower() for l in config["search"]["levels"]]
    domains = [d.lower() for d in config["search"]["domains"]]
    blocked_sites = config["search"].get("blocked_sites", [])
    india_code = config["search"].get("india_country_code", "in")
    global_loc = config["search"].get("global_search_loc", "Remote")
    remote_signals = [r.lower() for r in config["search"].get("remote_signals", [])]
    global_remote_signals = [gs.lower() for gs in config["search"].get("global_remote_signals", [])]
    india_sites = config["search"].get("india_sites", [])
    global_sites = config["search"].get("global_sites", [])
    hub_map_config = config["search"].get("hub_map", {})
    
    # DEEP DIVE CONFIG (Zero-Yield Hubs)
    deep_scrape_hubs = [h.lower() for h in config["search"].get("deep_scrape_hubs", [])]
    deep_scrape_limit = config["search"].get("deep_scrape_limit", 5)
    deep_scrape_keyword = config["search"].get("deep_scrape_keyword", "remote")
    deep_scrape_description_check = config["search"].get("deep_scrape_description_check", False)

    found_local = []
    found_india_remote = []
    found_global_remote = []

    all_tasks = []
    
    # 1. INDIA CITIES (Mandate 1 & 2)
    for loc in india_search_cities:
        all_tasks.append({"sites": india_sites, "country": india_code, "loc": loc})
            
    # 2. GLOBAL HUB GRID (Mandate 3)
    # OPTION B: Specialist Intelligence (Power 6 Hubs)
    # This replaces the noisy LinkedIn Worldwide search with 20+ specialized platforms.
    global_intel_raw = fetch_global_intelligence(config, levels, domains)
    for j in global_intel_raw:
        # Purity Audit: Standardize for categorization
        j['location'] = j.get('location', 'Remote')
        j['description'] = j.get('description', '') # Optional
        j['uid'] = hashlib.md5(j['job_url'].encode('utf-8')).hexdigest()
        j['fingerprint'] = f"{j['title'].lower()}|{j['company'].lower()}"
        
        # Deduplication & Bucketing
        if j['uid'] not in seen_ids and j['fingerprint'] not in seen_fingerprints:
            seen_ids.add(j['uid'])
            seen_fingerprints.add(j['fingerprint'])
            found_global_remote.append(j)

    for task in all_tasks:
        for term in search_terms:
            country_code = task["country"]
            search_loc = task["loc"]
            task_sites = [s for s in task["sites"] if s not in blocked_sites]
            if not task_sites: continue
            
            # --- DEEP DIVE STRATEGY (Zero-Yield Hubs) ---
            is_deep_dive = country_code.lower() in deep_scrape_hubs
            
            if is_deep_dive:
                # Relaxed Scraping: Disable platform filter, Force Keyword
                is_remote_task = False 
                term = f"{term} {deep_scrape_keyword}"
                rw = deep_scrape_limit
                print(f"  > [DEEP DIVE] Searching: '{term[:40]}...' in '{search_loc}' (Top {rw})")
            else:
                # Standard Logic: Platform Filter
                is_remote_task = (search_loc.lower() == global_loc.lower()) or (country_code != india_code)
                # Site-specific results depth calculation
                rw = config["search"].get("results_wanted", 30)
                if "naukri" in task_sites: rw = max(rw, config["search"].get("naukri_results_wanted", 0))
                if "indeed" in task_sites: rw = max(rw, config["search"].get("indeed_results_wanted", 0))
                print(f"  > Searching: '{term[:40]}...' in '{search_loc}' [{country_code}] via {task_sites}...")

            try:
                time.sleep(random.uniform(4, 6))
                
                res = scrape_jobs(
                    site_name=task_sites, 
                    search_term=term, 
                    location=search_loc, 
                    is_remote=is_remote_task,
                    results_wanted=rw,
                    hours_old=config["search"].get("hours_old", 24),
                    country_indeed=country_code
                )
                
                if res is not None and not res.empty:
                    new_results = res.to_dict('records')
                    for job in new_results:
                        title_str = str(job.get('title', '')).lower()
                        loc_str = str(job.get('location', '')).lower()
                        desc_str = str(job.get('description', '')).lower()
                        
                        # A. HUB-APPLICABILITY GUARD
                        if any(b in title_str or b in loc_str for b in blacklist):
                            continue

                        # B. SENIORITY WHITELIST (Strict Word Boundaries)
                        # Prevents "system" matching "em", "asset" matching "set", etc.
                        def has_word_match(text, term_list):
                            for term in term_list:
                                # Regex: \b = Word Boundary. 
                                # Matches "EM" but not "System". Matches "QA" but not "Aqua".
                                pattern = r'\b' + re.escape(term) + r'\b'
                                if re.search(pattern, text, re.IGNORECASE):
                                    return True
                            return False

                        has_level = has_word_match(title_str, levels)
                        has_domain = has_word_match(title_str, domains)
                        
                        if not (has_level and has_domain):
                            continue
                            
                        # --- DEEP DIVE JD CHECK ---
                        if is_deep_dive and deep_scrape_description_check:
                            # Must verify "Remote" in description since we disabled platform filter
                            # Also check title/location for redundancy
                            has_remote_kw = any(r in desc_str or r in title_str or r in loc_str for r in remote_signals)
                            if not has_remote_kw:
                                # DISCARD: Local job caught by relaxed scraping
                                continue

                        # C. ID & CATEGORIZATION
                        jurl = job.get('job_url', '')
                        if not jurl: continue
                        
                        jid = hashlib.md5(jurl.encode('utf-8')).hexdigest()
                        company_str = str(job.get('company', '')).lower()
                        fingerprint = f"{title_str}|{company_str}"

                        if jid not in seen_ids and fingerprint not in seen_fingerprints:
                            job['uid'] = jid
                            job['fingerprint'] = fingerprint
                            seen_ids.add(jid)
                            seen_fingerprints.add(fingerprint)
                            
                            # --- 3-BUCKET CATEGORIZATION (Enablement Master Logic) ---
                            # Note: Reading Title/Location Header (not full JD)
                            has_global_signal = any(gs in title_str or gs in loc_str for gs in global_remote_signals)
                            is_remote_explicit = any(r in loc_str or r in title_str for r in remote_signals)
                            is_local_city = any(city in loc_str for city in india_city_aliases if city not in [global_loc.lower(), 'remote'])
                            
                            # JD Sniper (Rule 9): Immediate discard for residency-based signals
                            if any(rs in title_str or rs in loc_str for rs in residency_signals):
                                print(f"    [SNIPER DISCARD] Residency terms found in '{title_str[:30]}'.")
                                continue

                            # Hub-Integrity Check
                            hub_key = country_code.lower()
                            target_hub_terms = hub_map_config.get(hub_key, [hub_key])
                            # Final Rigor: Check title as well for hub names
                            is_hub_match = any(term in loc_str or term in title_str for term in target_hub_terms)
                            
                            # Rigorous India Check: 
                            # 1. Contains 'india' or a local city alias
                            # 2. OR is exactly 'remote'/'wfh' (common on Naukri) without foreign country text
                            is_india_job = ("india" in loc_str or is_local_city) or \
                                           (country_code == india_code and loc_str.strip() in ["remote", "wfh", "work from home", "telecommute"])
                            
                            if is_remote_explicit or is_remote_task:
                                # Categorize as Remote
                                if country_code == india_code:
                                    # Naukri/India Bypass
                                    if has_global_signal:
                                        job['location'] = f"{loc_str} [Signal: Global-In-India]"
                                        found_global_remote.append(job)
                                    elif is_india_job:
                                        job['location'] = f"{loc_str} [Signal: India-Remote]"
                                        found_india_remote.append(job)
                                    else:
                                        print(f"    [LEAK DISCARD] International job '{title_str[:30]}' in India task.")
                                elif country_code == "worldwide":
                                    job['location'] = f"{loc_str} [Signal: Worldwide Task]"
                                    found_global_remote.append(job)
                                elif has_global_signal:
                                    # Identify which signal triggered it
                                    sig = next((s for s in global_remote_signals if s in title_str or s in loc_str), "Global")
                                    job['location'] = f"{loc_str} [Signal: {sig}]"
                                    found_global_remote.append(job)
                                else:
                                    # This is likely a 'Domestic-Only Remote' job in the hub country (Fodder)
                                    print(f"    [FODDER DISCARD] Domestic hub job '{title_str[:30]}' ({loc_str}) - No global signal.")
                            elif is_local_city:
                                found_local.append(job)
                            elif country_code == india_code and is_india_job:
                                # India local job fallback
                                found_local.append(job)
                            else:
                                # Non-remote global job or invalid leak -> DISCARD
                                continue
                
                time.sleep(1) # Cooldown between terms
            except Exception as e:
                print(f"    [SITE ERROR] '{task_sites}' failed: {str(e)[:100]}")
                continue

    total_found = len(found_local) + len(found_india_remote) + len(found_global_remote)
    
    # --- FINAL QUALITY GATE (The Trash Compactor) ---
    def finalize_list(job_list):
        clean_list = []
        sniped_list = []
        for j in job_list:
            t = str(j.get('title', '')).lower()
            c = str(j.get('company', '')).lower()
            l = str(j.get('location', '')).lower()
            
            reason = None
            # 1. Final Blacklist pass (Check Company too)
            for b in blacklist:
                if b in t or b in l or b in c:
                    reason = f"Blacklist: {b}"
                    break
            
            # 2. Strict Seniority check
            if not reason:
                if any(jr in t for jr in ["assistant", "junior", "trainee", "associate"]):
                    if not ("senior associate" in t or "lead associate" in t):
                        reason = "Junior/Associate Role"

            if reason:
                j['sniped_reason'] = reason
                sniped_list.append(j)
            else:
                clean_list.append(j)
                
        return clean_list, sniped_list

    found_local, sniped_local = finalize_list(found_local)
    found_india_remote, sniped_india = finalize_list(found_india_remote)
    found_global_remote, sniped_global = finalize_list(found_global_remote)

    total_applicable = len(found_local) + len(found_india_remote) + len(found_global_remote)
    print(f"\n--- DONE. Found {total_found} New (Scraped) | {total_applicable} Applicable ---")

    if found_local: send_email(f"Local Alert: {len(found_local)} New City Roles", found_local, config, sniped_local)
    if found_india_remote: send_email(f"India Remote Alert: {len(found_india_remote)} New Remote Roles", found_india_remote, config, sniped_india)
    if found_global_remote: send_email(f"Global Remote Alert: {len(found_global_remote)} New Global Remote Roles", found_global_remote, config, sniped_global)

    if total_applicable > 0:
        for j in found_local + found_india_remote + found_global_remote:
            history.append({
                "id": j['uid'], 
                "fingerprint": j.get('fingerprint'),
                "date": datetime.now().isoformat()
            })
        save_history(history, config)
    
    return True

if __name__ == "__main__":
    if not run():
        sys.exit(1)
