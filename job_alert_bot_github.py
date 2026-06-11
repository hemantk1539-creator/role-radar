"""
job_alert_bot_github.py - pipeline entrypoint / orchestrator.

This file wires the four modules together and owns run() - the end-to-end flow:
  config -> global intel burst -> India parallel scrape -> dedup/bucket ->
  final quality gate -> per-bucket email -> history persistence.

The actual logic lives in cohesive, unit-tested modules:
  config.py    - YAML + job_history.json I/O
  filters.py   - title/location qualification (pure)
  scrapers.py  - outbound fetchers (JobSpy + Power 6 hubs)
  emailer.py   - HTML digest + SMTP

This stays the entrypoint deploy.py imports and the GitHub Actions workflow runs.
"""
import os
import sys
import time
import random
import hashlib
import concurrent.futures
import dateutil.parser
from datetime import datetime, date

from config import load_config, load_history, save_history
from filters import india_is_applicable, finalize_list, categorize_job
from scrapers import fetch_global_intelligence, scrape_jobs
from emailer import send_email


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
    global_dropped_dedup = 0

    for j in global_intel_raw:
        if not j.get('job_url'): continue

        # Freshness Check (Rule 19): respect global_hours_old for API/RSS results
        if j.get('date'):
            try:
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
            print(f"    [Global New]   \"{j.get('title', '?')}\" @ {j.get('company', '?')}")
        else:
            global_dropped_dedup += 1
            print(f"    [Global Dedup] \"{j.get('title', '?')}\" @ {j.get('company', '?')}")

    print(f"  [Global Filter] Kept {global_kept} new | Dropped {global_dropped_age} stale (> {global_hrs}h) | Dropped {global_dropped_dedup} dedup.")

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

    for j in sniped_local + sniped_india + sniped_global:
        print(f"  [Sniped] \"{j.get('title', '?')}\" @ {j.get('company', '?')} ({j.get('sniped_reason', '?')})")

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
