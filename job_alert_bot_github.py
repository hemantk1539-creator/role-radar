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
import concurrent.futures
from html import escape as _html_escape  # module-level alias - NOT `import html`, because send_email
                                         # uses a local variable named `html` that would shadow the module.

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
        except (json.JSONDecodeError, ValueError, OSError) as e:
            print(f"[WARN] History file corrupt or unreadable: {e}")
            return []
    return []

def save_history(history, config):
    max_h = config["search"].get("max_history", 2000)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-max_h:], f, indent=4)

def is_match(title, levels, domains, block_anchors):
    t = title.lower()
    has_level = any(re.search(r'\b' + re.escape(l) + r'\b', t, re.IGNORECASE) for l in levels)
    has_domain = any(re.search(r'\b' + re.escape(d) + r'\b', t, re.IGNORECASE) for d in domains)
    is_blocked = any(re.search(r'\b' + re.escape(b) + r'\b', t, re.IGNORECASE) for b in block_anchors)
    return has_level and has_domain and not is_blocked

def has_word_match(text, term_list):
    for term in term_list:
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def india_is_applicable(title_str, loc_str, levels, domains, blacklist, block_anchors=()):
    """India-side applicability gate (pure, unit-tested).

    Mirrors the global is_match() contract for the India pipeline, which previously
    duplicated this logic inline inside run(). Returns True to KEEP a role, False to DROP.

      A.  blacklist hit on title OR location          -> drop
      B.  needs a seniority word AND a domain word     -> else drop
      B2. negative-domain block_anchors hit on title   -> drop
          (defaults to empty = NO-OP; populated in a later step for noise filtering)

    Inputs are expected pre-lowercased by the caller; has_word_match is case-insensitive anyway.
    """
    # A. HUB-APPLICABILITY GUARD
    if has_word_match(title_str, blacklist) or has_word_match(loc_str, blacklist):
        return False
    # B. SENIORITY + DOMAIN WHITELIST (strict word boundaries)
    if not (has_word_match(title_str, levels) and has_word_match(title_str, domains)):
        return False
    # B2. NEGATIVE-DOMAIN BLOCK ANCHORS (no-op until populated in Step 2)
    if block_anchors and has_word_match(title_str, block_anchors):
        return False
    return True

def finalize_list(job_list, blacklist):
    clean_list = []
    sniped_list = []
    for j in job_list:
        t = str(j.get('title', '')).lower()
        c = str(j.get('company', '')).lower()
        l = str(j.get('location', '')).lower()
        reason = None
        for b in blacklist:
            pattern = r'\b' + re.escape(b) + r'\b'
            if re.search(pattern, t) or re.search(pattern, l) or re.search(pattern, c):
                reason = f"Blacklist: {b}"
                break
        if not reason:
            # Word-boundary (\b) matching - NOT substring - so "associate" never trips on "associated".
            if has_word_match(t, ["assistant", "junior", "trainee", "associate"]):
                if not has_word_match(t, ["senior associate", "lead associate"]):
                    reason = "Junior/Associate Role"
        if reason:
            j['sniped_reason'] = reason
            sniped_list.append(j)
        else:
            clean_list.append(j)
    return clean_list, sniped_list

def categorize_job(title_str, loc_str, country_code, india_code, global_loc,
                   remote_signals, global_remote_signals, india_city_aliases, residency_signals):
    """Routes a job to a bucket. Returns (bucket, signal) or (None, None) to drop."""
    if any(rs in title_str or rs in loc_str for rs in residency_signals):
        return None, None
    has_global_signal = any(gs in title_str or gs in loc_str for gs in global_remote_signals)
    is_remote_explicit = any(r in loc_str or r in title_str for r in remote_signals)
    is_local_city = any(city in loc_str for city in india_city_aliases if city not in [global_loc.lower(), 'remote'])
    is_hybrid_signal = any(h in loc_str or h in title_str for h in ["hybrid", "flexible", "flex", "partially", "office optional", "wfo"])
    is_india_job = ("india" in loc_str or is_local_city) or \
                   (country_code == india_code and loc_str.strip() in ["remote", "wfh", "work from home", "telecommute", "pan india"])
    if is_remote_explicit:
        if country_code == india_code:
            if has_global_signal:
                return "global_remote", "Global-In-India"
            elif is_local_city:
                return "local", f"{'Hybrid' if is_hybrid_signal else 'Remote'}-Local"
            elif is_india_job:
                return "india_remote", "India-WFA"
        elif country_code == "worldwide":
            return "global_remote", "Worldwide Task"
        elif has_global_signal:
            sig = next((s for s in global_remote_signals if s in title_str or s in loc_str), "Global")
            return "global_remote", sig
    elif is_local_city:
        return "local", None
    elif country_code == india_code and is_india_job:
        return "local", None
    return None, None

def fetch_json(source, url, levels, domains, block_anchors):
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            results = []
            for j in data.get("jobs", []):
                title = j.get("title") or j.get("name") or j.get("text")
                if title and is_match(title, levels, domains, block_anchors):
                    results.append({
                        "title": title,
                        "company": j.get("companyName") or j.get("company_name") or j.get("company") or source,
                        "location": j.get('location', 'Remote'),
                        "signal": f"[Signal: {source}]",
                        "job_url": j.get("applicationLink") or j.get("url") or j.get("application_url"),
                        "site": source.lower(),
                        "date": j.get("pubDate") or j.get("published_at", "")
                    })
            print(f"  [Hub] {source}: Found {len(results)} potential roles.")
            return results
    except Exception as e:
        print(f"  [Hub] {source}: Error - {str(e)[:80]}")
        return []
    return []

def fetch_rss(source, url, levels, domains, block_anchors):
    try:
        feed = feedparser.parse(url)
        results = []
        for entry in feed.entries:
            title = entry.get("title", "")
            if is_match(title, levels, domains, block_anchors):
                results.append({
                    "title": title,
                    "company": entry.get("author") or source,
                    "location": "Remote",
                    "signal": f"[Signal: {source}]",
                    "job_url": entry.get("link"),
                    "site": source.lower(),
                    "date": entry.get("published", "")
                })
        print(f"  [Hub] {source}: Found {len(results)} potential roles.")
        return results
    except Exception as e:
        print(f"  [Hub] {source}: RSS Error - {str(e)[:80]}")
        return []

def fetch_ats(ats_type, token, levels, domains, block_anchors):
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs" if ats_type == "greenhouse" else \
              f"https://api.lever.co/v0/postings/{token}" if ats_type == "lever" else \
              f"https://api.ashbyhq.com/posting-api/job-board/{token}" if ats_type == "ashby" else \
              f"https://{token}.breezy.hr/json" if ats_type == "breezy" else \
              f"https://{token}.pinpointvis.com/api/v1/jobs"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            results = []
            data = res.json()
            job_list = data if isinstance(data, list) else data.get("jobs", [])
            for j in job_list:
                title = j.get("title") or j.get("text") or j.get("name")
                if title and is_match(title, levels, domains, block_anchors):
                    url_key = "absolute_url" if ats_type in ["greenhouse", "pinpoint"] else \
                              "hostedUrl" if ats_type == "lever" else \
                              "job_url" if ats_type == "ashby" else "url"
                    results.append({"title": title, "company": token.capitalize(), "location": "Remote",
                                    "signal": f"[Signal: ATS-{token}]", "job_url": j.get(url_key),
                                    "site": f"ats-{token}", "date": j.get("updated_at") or j.get("createdAt", "")})
            print(f"  [ATS] {token}: Found {len(results)} matches.")
            return results
    except Exception as e:
        print(f"  [ATS] {token}: Error - {str(e)[:80]}")
        return []
    return []

def fetch_global_intelligence(config, levels, domains):
    """
    POWER 6 HUB: The Centralized Global Remote Intelligence Layer.
    v1.7: Parallel Burst Engine (Zero-Loss Efficiency).
    """
    print("\n--- GLOBAL INTELLIGENCE: PARALLEL BURST FROM 23+ PLATFORMS ---")
    start_time = time.time()
    jobs = []
    
    block_anchors = config["search"].get("global_block_anchors", [])

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = []
        # 1. APIs
        futures.append(executor.submit(fetch_json, "Himalayas", config["search"].get("himalayas_api"), levels, domains, block_anchors))
        futures.append(executor.submit(fetch_json, "Remote.com", config["search"].get("remote_com_api"), levels, domains, block_anchors))
        futures.append(executor.submit(fetch_json, "Deel", config["search"].get("deel_api"), levels, domains, block_anchors))
        # 2. RSS
        feeds = [("WWR", config["search"].get("wwr_feed")), ("JS-Remotely", config["search"].get("js_remotely_feed")), ("Arc.dev", config["search"].get("arc_dev_feed")), ("Wellfound", config["search"].get("wellfound_feed")), ("YC", config["search"].get("yc_api")), ("Remotive", config["search"].get("remotive_api"))]
        for s, u in feeds:
            if u: futures.append(executor.submit(fetch_rss, s, u, levels, domains, block_anchors))
        # 3. Direct ATS
        ats_atlas = config["search"].get("ats_atlas", {})
        for ats_type in ats_atlas:
            for token in ats_atlas[ats_type]:
                futures.append(executor.submit(fetch_ats, ats_type, token, levels, domains, block_anchors))

        for future in concurrent.futures.as_completed(futures):
            jobs.extend(future.result())

    print(f"--- POWER 6 COMPLETE. Found {len(jobs)} Pre-Sniper Roles in {time.time()-start_time:.2f}s ---\n")
    return jobs

def send_email(subject, jobs, config):
    if not jobs: return False
    # Escape scraped values before embedding in HTML (e.g. "R&D", "QA <Contract>"). Uses the
    # module-level _html_escape alias - the local `html` string var below shadows the html module.
    def esc(v):
        return _html_escape(str(v if v is not None else ""))
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
            html += f"<tr style='background-color: {t_info['color']}; color: white;'><th>Title</th><th>Company</th><th>Location</th><th>Signal</th><th style='width: 80px;'>Action</th></tr>"
            for job in tiers[t_key]:
                html += f"<tr style='border-bottom: 1px solid #eee;'>"
                html += f"<td><b>{esc(job.get('title'))}</b></td>"
                html += f"<td>{esc(job.get('company'))}</td>"
                html += f"<td>{esc(job.get('location'))}</td>"
                html += f"<td style='color: #7f8c8d; font-size: 0.85em;'>{esc(job.get('signal'))}</td>"
                html += f"<td style='text-align: center;'><a href='{esc(job.get('job_url'))}' style='background-color: {t_info['color']}; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 0.85em;'>{t_info['btn']}</a></td>"
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
            html += f"<tr style='background-color: {t_data['color']}; color: white;'><th>Title</th><th>Company</th><th>Location (Signal)</th><th>Site</th><th style='width: 80px;'>Action</th></tr>"
            for job in in_jobs[p_key]:
                html += f"<tr style='border-bottom: 1px solid #eee;'>"
                html += f"<td><b>{esc(job.get('title'))}</b></td>"
                html += f"<td>{esc(job.get('company'))}</td>"
                html += f"<td style='color: #666; font-size: 0.9em;'>{esc(job.get('location'))}</td>"
                html += f"<td style='color: #7f8c8d; font-size: 0.85em; text-transform: capitalize;'>{esc(job.get('site'))}</td>"
                html += f"<td style='text-align: center;'><a href='{esc(job.get('job_url'))}' style='background-color: #3498db; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 0.85em;'>Apply</a></td>"
                html += f"</tr>"
            html += "</table></div>"
    
    html += "<div style='margin-top: 30px; text-align: center; color: #95a5a6; font-size: 0.8em; border-top: 1px solid #eee; padding-top: 20px;'>"
    html += "This is an automated intelligence report from your Job Alert Bot v1.2. Hub Logic: Power 6 Tiered Grid.</div></div>"
    
    msg.attach(MIMEText(html, "html"))

    try:
        print(f"  [MAIL] Connecting to SMTP for '{subject}'...")
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
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
    blacklist = [b.lower() for b in config["search"]["blacklist"]]
    # JD Sniper Terms (Rule 9)
    residency_signals = [r.lower() for r in config["search"].get("residency_signals", [])]
    
    levels = [l.lower() for l in config["search"]["levels"]]
    domains = [d.lower() for d in config["search"]["domains"]]
    india_block_anchors = [b.lower() for b in config["search"].get("india_block_anchors", [])]
    blocked_sites = config["search"].get("blocked_sites", [])
    india_code = config["search"].get("india_country_code", "in")
    global_loc = config["search"].get("global_search_loc", "Remote")
    remote_signals = [r.lower() for r in config["search"].get("remote_signals", [])]
    global_remote_signals = [gs.lower() for gs in config["search"].get("global_remote_signals", [])]
    # PARKED (2026-06-10): global_hubs / india_sites / global_sites / hub_map / deep_scrape_* config keys
    # are intentionally NOT loaded here - no feature wires them yet. Keys kept + annotated in the YAML.
    # Re-add the load line when the corresponding feature is built.

    found_local = []
    found_india_remote = []
    found_global_remote = []

    # 1. GLOBAL INTEL (Parallel API Burst)
    global_intel_raw = fetch_global_intelligence(config, levels, domains)
    global_hrs = config["search"].get("global_hours_old", 72)
    now_ts = time.time()
    
    global_kept = 0
    global_dropped_age = 0

    for j in global_intel_raw:
        if not j.get('job_url'): continue
        
        # Freshness Check (Rule 19): respect global_hours_old for API/RSS results
        if j.get('date'):
            try:
                import dateutil.parser
                job_ts = dateutil.parser.parse(j['date']).timestamp()
                if (now_ts - job_ts) / 3600 > global_hrs:
                    global_dropped_age += 1
                    continue
            except Exception: pass

        # JD Sniper (Rule 9) - Apply to API results too
        title_str = j.get('title', '').lower()
        if any(rs in title_str for rs in residency_signals):
            continue

        # Purity Audit: Standardize for categorization
        j['location'] = j.get('location', 'Remote')
        j['signal'] = j.get('signal', '[Signal: Global-Intel]')
        j['uid'] = hashlib.md5(j['job_url'].encode('utf-8')).hexdigest()
        j['fingerprint'] = f"{j['title'].lower()}|{j['company'].lower()}"
        
        # Deduplication & Bucketing
        if j['uid'] not in seen_ids and j['fingerprint'] not in seen_fingerprints:
            seen_ids.add(j['uid'])
            seen_fingerprints.add(j['fingerprint'])
            found_global_remote.append(j)
            global_kept += 1

    print(f"  [Global Filter] Kept {global_kept} new roles | Dropped {global_dropped_age} stale (> {global_hrs}h) roles.")

    # 2. INDIA & CITIES (Parallel v3.0)
    all_tasks = []
    for loc in india_search_cities:
        # LinkedIn and Naukri (Standard 4-burst)
        all_tasks.append({"sites": ["linkedin", "naukri"], "country": india_code, "loc": loc})
        # Indeed (Optimized 2-burst)
        all_tasks.append({"sites": ["indeed"], "country": india_code, "loc": loc})

    def execute_scrape(task):
        print(f"    [India Worker] Scraping {task['loc']} on {', '.join(task['sites'])}...")
        task_results = []
        active_terms = search_terms
        if "indeed" in task["sites"] and len(task["sites"]) == 1:
            # Consolidation: Combine search terms in pairs dynamically
            active_terms = []
            for i in range(0, len(search_terms), 2):
                if i + 1 < len(search_terms):
                    active_terms.append(f"({search_terms[i]}) OR ({search_terms[i+1]})")
                else:
                    active_terms.append(search_terms[i])

        for term in active_terms:
            country_code = task["country"]
            search_loc = task["loc"]
            task_sites = [s for s in task["sites"] if s not in blocked_sites]
            if not task_sites: continue
            
            try:
                # Conservative delay for parallel safety
                time.sleep(random.uniform(3, 5))
                
                res = scrape_jobs(
                    site_name=task_sites, 
                    search_term=term, 
                    location=search_loc, 
                    results_wanted=config["search"].get("results_wanted", 30) if "naukri" not in task_sites else config["search"].get("naukri_results_wanted", 0),
                    hours_old=config["search"].get("hours_old", 24),
                    country_indeed=country_code
                )
                
                if res is not None and not res.empty:
                    task_results.extend(res.to_dict('records'))
            except Exception as e:
                print(f"    [India Worker] Scrape error ({task['loc']}, {str(term)[:30]}): {str(e)[:80]}")
        return task_results, task["loc"], task["country"]

    print(f"  > Launching Parallel India Engine (3 Workers)...")
    india_kept = 0
    india_dropped_age = 0
    india_hrs = config["search"].get("hours_old", 24)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(execute_scrape, t): t for t in all_tasks}
        for future in concurrent.futures.as_completed(futures):
            try:
                new_results, search_loc, country_code = future.result()
                for job in new_results:
                    # Double-Lock Freshness (Rule 19): catch platform leaks
                    if job.get('date_posted'):
                        try:
                            import dateutil.parser
                            from datetime import date
                            posted_dt = job['date_posted']
                            if isinstance(posted_dt, str):
                                posted_dt = dateutil.parser.parse(posted_dt).date()
                            days_old = (date.today() - posted_dt).days
                            if days_old > 1: # Beyond 24-48h window
                                india_dropped_age += 1
                                continue
                        except Exception: pass

                    title_str = str(job.get('title', '')).lower()
                    loc_str = str(job.get('location', '')).lower()
                    


                    # A+B APPLICABILITY GATE - extracted to module-level india_is_applicable() (unit-tested).
                    # block_anchors intentionally NOT passed yet (Step 2); behaviour is identical for now.
                    if not india_is_applicable(title_str, loc_str, levels, domains, blacklist, india_block_anchors):
                        continue
                        
                    # C. ID & CATEGORIZATION
                    jurl = job.get('job_url', '')
                    if not jurl: continue
                    
                    jid = hashlib.md5(jurl.encode('utf-8')).hexdigest()
                    company_str = str(job.get('company', '')).lower()
                    fingerprint = f"{title_str}|{company_str}|{search_loc.lower()}"

                    if jid in seen_ids or fingerprint in seen_fingerprints:
                        continue

                    job['uid'] = jid
                    job['fingerprint'] = fingerprint
                    seen_ids.add(jid)
                    seen_fingerprints.add(fingerprint)
                    
                    # --- 3-BUCKET CATEGORIZATION (v1.3 Intelligence) ---
                    bucket, signal = categorize_job(
                        title_str, loc_str, country_code, india_code, global_loc,
                        remote_signals, global_remote_signals, india_city_aliases, residency_signals
                    )
                    if bucket:
                        if signal:
                            job['location'] = f"{loc_str} [Signal: {signal}]"
                        if bucket == "global_remote":
                            found_global_remote.append(job)
                        elif bucket == "local":
                            found_local.append(job)
                        elif bucket == "india_remote":
                            found_india_remote.append(job)
                        india_kept += 1  # count only bucketed roles (was overcounting no-bucket drops)
            except Exception as e:
                print(f"    [THREAD ERROR] Worker failed: {str(e)[:100]}")
                continue

    print(f"  [India Filter] Kept {india_kept} new roles | Dropped {india_dropped_age} stale leaks (> {india_hrs}h).")

    total_found = len(found_local) + len(found_india_remote) + len(found_global_remote)

    
    # --- FINAL QUALITY GATE (The Trash Compactor) ---
    found_local, sniped_local = finalize_list(found_local, blacklist)
    found_india_remote, sniped_india = finalize_list(found_india_remote, blacklist)
    found_global_remote, sniped_global = finalize_list(found_global_remote, blacklist)

    total_applicable = len(found_local) + len(found_india_remote) + len(found_global_remote)
    print(f"\n--- DONE. Found {total_found} New (Scraped) | {total_applicable} Applicable ---")

    if found_local: send_email(f"Local Alert: {len(found_local)} New City Roles", found_local, config)
    if found_india_remote: send_email(f"India Remote Alert: {len(found_india_remote)} New Remote Roles", found_india_remote, config)
    if found_global_remote: send_email(f"Global Remote Alert: {len(found_global_remote)} New Global Remote Roles", found_global_remote, config)

    sniped_all = sniped_local + sniped_india + sniped_global
    if total_applicable > 0 or sniped_all:
        for j in found_local + found_india_remote + found_global_remote + sniped_all:
            uid = j.get('uid')
            if not uid:
                continue
            history.append({
                "id": uid,
                "fingerprint": j.get('fingerprint'),
                "date": datetime.now().isoformat()
            })
        save_history(history, config)
    
    return True

if __name__ == "__main__":
    if not run():
        sys.exit(1)
