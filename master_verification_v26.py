import os, yaml, hashlib, time, re
from jobspy import scrape_jobs
from job_alert_bot_github import fetch_global_intelligence

def run_master_audit():
    print("--- 🛡️ V2.6 MASTER INTEGRITY AUDIT STARTING ---")
    with open("job_alert_config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    search_terms = config['search']['search_terms']
    levels = config['search']['levels']
    domains = config['search']['domains']
    
    print("\n[1/3] Auditing Sniper for Contradictions...")
    test_titles = [
        "Director Software Quality", "QA Manager", "Senior Engineering Manager - Automation", 
        "VP of Quality", "Project Manager", "Product Manager Quality", "GRC Lead", "SAP QA"
    ]
    
    def mock_sniper(title):
        t = title.lower()
        has_level = any(re.search(r'\b' + re.escape(l) + r'\b', t) for l in levels)
        has_domain = any(re.search(r'\b' + re.escape(d) + r'\b', t) for d in domains)
        block_anchors = ["product", "project", "program", "sap", "scrum", "grc", "legal"]
        is_blocked = any(re.search(r'\b' + re.escape(b) + r'\b', t) for b in block_anchors)
        return has_level and has_domain and not is_blocked

    for title in test_titles:
        result = "PASSED" if mock_sniper(title) else "SNIPED"
        print(f"  > Title: '{title}' -> {result}")

    print("\n[2/3] Auditing Power 6 Hubs (23+ Platforms)...")
    try:
        global_jobs = fetch_global_intelligence(config, levels, domains)
        print(f"  > Power 6 found {len(global_jobs)} applicable global roles.")
    except Exception as e:
        print(f"  > Power 6 Error: {e}")

    print("\n[3/3] Auditing India Saturation (Bengaluru sample)...")
    test_term = search_terms[0]
    print(f"  > Searching Intersection: {test_term}")
    try:
        res = scrape_jobs( site_name=["linkedin"], search_term=test_term, location="Bengaluru", results_wanted=10, hours_old=72, country_indeed='india' )
        if res is not None and not res.empty:
            print(f"  > Captured {len(res)} roles in Bengaluru.")
            for i, row in res.head(3).iterrows():
                print(f"    - Found: {row['title']} at {row['company']}")
        else: print("  > No results found in city test.")
    except Exception as e: print(f"  > City Test Error: {e}")
    print("\n--- AUDIT COMPLETE ---")

if __name__ == "__main__":
    run_master_audit()
