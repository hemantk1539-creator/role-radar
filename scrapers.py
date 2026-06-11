"""
scrapers.py - all outbound data acquisition.

Holds the JobSpy import + monkey-patch and the parallel "Power 6" hub fetchers
(JSON APIs, RSS feeds, direct ATS boards). `scrape_jobs` is re-exported so the
India engine in the pipeline can use it without importing jobspy directly.

Test seam: tests patch `scrapers.requests.get` / `scrapers.feedparser.parse` - the
module-level imports below are what those patch paths resolve against.
"""
import sys
import time
import requests
import feedparser
import concurrent.futures

from filters import is_match

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
