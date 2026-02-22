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
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def save_history(history, config):
    max_h = config["search"].get("max_history", 2000)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
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
    
    # LOAD UI STRATEGY FROM CONFIG
    hub_map = config["search"].get("global_hub_map", {})
    india_tier_cfg = config["search"].get("india_tiers", {})
    global_tier_cfg = config["search"].get("global_tiers", {})

    html = f"<div style='font-family: Arial, sans-serif; color: #333; max-width: 800px; margin: auto;'>"
    html += f"<div style='background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px 8px 0 0;'>"
    html += f"<h1 style='margin: 0; font-size: 24px;'>{subject}</h1>"
    html += f"<p style='margin: 5px 0 0; opacity: 0.8;'>EM/Director Intelligence Report | {datetime.now().strftime('%Y-%m-%d')}</p></div>"

    if "Global" in subject:
        # Group jobs by Tier
        tiers = {"tier1": [], "tier2": [], "tier3": [], "tier4": []}
        for j in jobs:
            s = j.get('site', '').lower()
            tier_key = "tier1" if s.startswith("ats") else "tier1" if s in ["deel", "remote.com"] else \
                       "tier2" if s in ["yc", "wellfound", "arc.dev", "otta"] else \
                       "tier3" if s in ["wwr", "js_remotely"] else "tier4"
            tiers[tier_key].append(j)
        
        for t_key in ["tier1", "tier2", "tier3", "tier4"]:
            if not tiers[t_key]: continue
            t_info = global_tier_cfg.get(t_key, {"name": t_key, "color": "#333", "btn": "Link"})
            html += f"<div style='margin-top: 30px;'>"
            html += f"<h3 style='color: {t_info['color']}; border-left: 5px solid {t_info['color']}; padding-left: 10px; margin-bottom: 15px;'>{t_info['name']}</h3>"
            html += "<table border='0' cellpadding='10' style='border-collapse: collapse; width: 100%; box-shadow: 0 2px 5px rgba(0,0,0,0.1);'>"
            html += f"<tr style='background-color: {t_info['color']}; color: white;'><th>Title</th><th>Company</th><th>Signal</th><th style='width: 80px;'>Action</th></tr>"
            for job in tiers[t_key]:
                html += f"<tr style='border-bottom: 1px solid #eee;'>"
                html += f"<td><b>{job.get('title')}</b></td>"
                html += f"<td>{job.get('company')}</td>"
                html += f"<td style='color: #7f8c8d; font-size: 0.85em;'>{job.get('location')}</td>"
                html += f"<td style='text-align: center;'><a href='{job.get('job_url')}' style='background-color: {t_info['color']}; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 0.85em;'>{t_info['btn']}</a></td>"
                html += f"</tr>"
            html += "</table></div>"
    else:
        # --- TRI-CATEGORY INDIA BUCKETING ---
        in_jobs = {"prio1": [], "prio2": [], "prio3": []}
        for j in jobs:
            loc = j.get('location', '').lower()
            if "hybrid" in loc or "remote-local" in loc: in_jobs["prio1"].append(j)
            elif "india-wfa" in loc or "wfa" in loc: in_jobs["prio2"].append(j)
            else: in_jobs["prio3"].append(j)

        for p_key in sorted(in_jobs.keys()):
            if not in_jobs[p_key]: continue
            t_data = india_tier_cfg.get(p_key, {"name": p_key, "color": "#333"})
            html += f"<div style='margin-top: 30px;'>"
            html += f"<h3 style='color: {t_data['color']}; border-left: 5px solid {t_data['color']}; padding-left: 10px; margin-bottom: 15px;'>{t_data['name']}</h3>"
            html += "<table border='0' cellpadding='10' style='border-collapse: collapse; width: 100%; box-shadow: 0 2px 5px rgba(0,0,0,0.1);'>"
            html += f"<tr style='background-color: {t_data['color']}; color: white;'><th>Title</th><th>Company</th><th>Location</th><th style='width: 80px;'>Action</th></tr>"
            for job in in_jobs[p_key]:
                html += f"<tr style='border-bottom: 1px solid #eee;'>"
                html += f"<td><b>{job.get('title')}</b></td>"
                html += f"<td>{job.get('company')}</td>"
                html += f"<td style='color: #666; font-size: 0.9em;'>{job.get('location')}</td>"
                html += f"<td style='text-align: center;'><a href='{job.get('job_url')}' style='background-color: #3498db; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 0.85em;'>Apply</a></td>"
                html += f"</tr>"
            html += "</table></div>"
    
    if sniped_jobs:
        html += "<div style='margin-top: 40px; padding: 15px; background-color: #fdf2f2; border-radius: 8px; border: 1px solid #fadbd8;'>"
        html += "<h4 style='color: #c0392b; margin-top: 0;'>🧪 SNIPER LOG (Transparency Pass)</h4>"
        html += "<p style='font-size: 0.85em; color: #7b241c;'>The following jobs were detected but automatically discarded based on your purity rules:</p>"
        html += "<table border='0' cellpadding='5' style='width: 100%; font-size: 0.8em; color: #666;'>"
        for j in sniped_jobs[:15]: # Show top 15 only to keep email clean
            html += f"<tr><td style='color: #c0392b;'><b>[{j.get('sniped_reason')}]</b></td><td>{j.get('title')}</td><td>{j.get('company')}</td></tr>"
        html += "</table></div>"

    html += "<div style='margin-top: 30px; text-align: center; color: #95a5a6; font-size: 0.8em; border-top: 1px solid #eee; padding-top: 20px;'>"
    html += "This is an automated intelligence report from your Job Alert Bot v1.2. Hub Logic: Power 6 Tiered Grid.</div></div>"
    
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
        if not j.get('job_url'): continue
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
                    hours_old=config["search"].get("hours_old", 48),
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

                        # RULE 9: Duplicate Sniper (Cross-Site Deduplication)
                        if jid in seen_ids or fingerprint in seen_fingerprints:
                            continue

                        job['uid'] = jid
                        job['fingerprint'] = fingerprint
                        seen_ids.add(jid)
                        seen_fingerprints.add(fingerprint)
                        
                        # --- 3-BUCKET CATEGORIZATION (v1.3 Intelligence) ---
                        has_global_signal = any(gs in title_str or gs in loc_str for gs in global_remote_signals)
                        is_remote_explicit = any(r in loc_str or r in title_str for r in remote_signals)
                        is_local_city = any(city in loc_str for city in india_city_aliases if city not in [global_loc.lower(), 'remote'])
                        is_hybrid_signal = any(h in loc_str or h in title_str for h in ["hybrid", "flexible", "flex", "partially", "office optional", "wfo"])
                        
                        # JD Sniper (Rule 9): Residency discard
                        if any(rs in title_str or rs in loc_str for rs in residency_signals):
                            continue

                        is_india_job = ("india" in loc_str or is_local_city) or \
                                       (country_code == india_code and loc_str.strip() in ["remote", "wfh", "work from home", "telecommute", "pan india"])
                        
                        if is_remote_explicit or is_remote_task:
                            # Categorize as Remote
                            if country_code == india_code:
                                if has_global_signal:
                                    job['location'] = f"{loc_str} [Signal: Global-In-India]"
                                    found_global_remote.append(job)
                                elif is_local_city:
                                    # HYBRID/REMOTE-LOCAL PRIORITY
                                    sig_type = "Hybrid" if is_hybrid_signal else "Remote"
                                    job['location'] = f"{loc_str} [Signal: {sig_type}-Local]"
                                    found_local.append(job)
                                elif is_india_job:
                                    job['location'] = f"{loc_str} [Signal: India-WFA]"
                                    found_india_remote.append(job)
                                else:
                                    # International leak in India task
                                    continue
                            elif country_code == "worldwide":
                                job['location'] = f"{loc_str} [Signal: Worldwide Task]"
                                found_global_remote.append(job)
                            elif has_global_signal:
                                sig = next((s for s in global_remote_signals if s in title_str or s in loc_str), "Global")
                                job['location'] = f"{loc_str} [Signal: {sig}]"
                                found_global_remote.append(job)
                            else:
                                # Domestic fodder (e.g. US Remote only)
                                continue
                        elif is_local_city:
                            found_local.append(job)
                        elif country_code == india_code and is_india_job:
                            found_local.append(job)
                        else:
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
