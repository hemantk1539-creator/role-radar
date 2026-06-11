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
import threading
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


class SourceAudit:
    """Thread-safe per-source outcome collector for the global burst.

    Each source records exactly one outcome per run: 'ok' (returned >=1 role),
    'empty' (reachable but zero matches after filtering), or 'error' (unreachable
    or failed). Observational only - it never affects what is fetched or returned.
    Lets the end-of-burst summary show which of the configured boards are actually
    live, so dead ones can be pruned and the real source count is measurable.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.results = {}  # label -> (outcome, count)

    def record(self, label, outcome, count=0):
        with self._lock:
            self.results[label] = (outcome, count)

    def summary(self):
        """Returns (ok, empty, error) - sorted lists of source labels."""
        ok = sorted(s for s, (o, _) in self.results.items() if o == "ok")
        empty = sorted(s for s, (o, _) in self.results.items() if o == "empty")
        error = sorted(s for s, (o, _) in self.results.items() if o == "error")
        return ok, empty, error


def fetch_json(source, url, levels, domains, block_anchors, audit=None):
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
            if audit is not None:
                audit.record(source, "ok" if results else "empty", len(results))
            return results
        if audit is not None:
            audit.record(source, "error")
    except Exception as e:
        print(f"  [Hub] {source}: Error - {str(e)[:80]}")
        if audit is not None:
            audit.record(source, "error")
        return []
    return []


def fetch_rss(source, url, levels, domains, block_anchors, audit=None):
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
        if audit is not None:
            audit.record(source, "ok" if results else "empty", len(results))
        return results
    except Exception as e:
        print(f"  [Hub] {source}: RSS Error - {str(e)[:80]}")
        if audit is not None:
            audit.record(source, "error")
        return []


def fetch_ats(ats_type, token, levels, domains, block_anchors, audit=None):
    label = f"{ats_type}/{token}"
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
            if audit is not None:
                audit.record(label, "ok" if results else "empty", len(results))
            return results
        if audit is not None:
            audit.record(label, "error")
    except Exception as e:
        print(f"  [ATS] {token}: Error - {str(e)[:80]}")
        if audit is not None:
            audit.record(label, "error")
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
    audit = SourceAudit()

    block_anchors = config["search"].get("global_block_anchors", [])

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = []
        # 1. APIs
        futures.append(executor.submit(fetch_json, "Himalayas", config["search"].get("himalayas_api"), levels, domains, block_anchors, audit))
        futures.append(executor.submit(fetch_json, "Remote.com", config["search"].get("remote_com_api"), levels, domains, block_anchors, audit))
        futures.append(executor.submit(fetch_json, "Deel", config["search"].get("deel_api"), levels, domains, block_anchors, audit))
        # 2. RSS
        feeds = [("WWR", config["search"].get("wwr_feed")), ("JS-Remotely", config["search"].get("js_remotely_feed")), ("Arc.dev", config["search"].get("arc_dev_feed")), ("Wellfound", config["search"].get("wellfound_feed")), ("YC", config["search"].get("yc_api")), ("Remotive", config["search"].get("remotive_api"))]
        for s, u in feeds:
            if u: futures.append(executor.submit(fetch_rss, s, u, levels, domains, block_anchors, audit))
        # 3. Direct ATS
        ats_atlas = config["search"].get("ats_atlas", {})
        for ats_type in ats_atlas:
            for token in ats_atlas[ats_type]:
                futures.append(executor.submit(fetch_ats, ats_type, token, levels, domains, block_anchors, audit))

        for future in concurrent.futures.as_completed(futures):
            jobs.extend(future.result())

    ok, empty, error = audit.summary()
    total = len(ok) + len(empty) + len(error)
    print(f"--- POWER 6 COMPLETE. Found {len(jobs)} Pre-Sniper Roles in {time.time()-start_time:.2f}s ---")
    print(f"  [Source Audit] {total} sources hit | {len(ok)} returned roles | {len(empty)} reachable, zero-match | {len(error)} errored.")
    if error:
        print(f"  [Source Audit] Errored ({len(error)}): {', '.join(error)}")
    if empty:
        print(f"  [Source Audit] Zero-match ({len(empty)}): {', '.join(empty)}")
    print()
    return jobs
