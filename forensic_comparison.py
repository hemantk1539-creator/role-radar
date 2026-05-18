import os, yaml, hashlib, time, re
from jobspy import scrape_jobs

def forensic_strict_comparison():
    print("--- 🛡️ RIGID (Old Phrases) vs ELASTIC (New v2.8.2) YIELD TEST ---")
    
    # 1. RIGID: The long list with "Software Development Engineer in Test", etc.
    # Note: I'm combining them with 'Manager' to keep the result set focused.
    rigid_term = '(Manager AND ("Quality Engineering" OR "Quality Assurance" OR "Software Quality" OR "Automation" OR "QA" OR "QE" OR "SDET" OR "SET" OR "Software Test" OR "Software Development Engineer in Test" OR "Software Engineer in Test" OR "Quality" OR "Test" OR "Testing"))'
    
    # 2. ELASTIC (v2.8.2): The compressed list under 250 chars
    elastic_term = '(Manager AND (Quality OR QA OR QE OR SDET OR SET OR Test OR Testing OR Automation OR "Quality Engineering" OR "Quality Assurance" OR "Software Quality" OR "Software Test"))'

    def run_search(term, label):
        print(f"\n[SEARCH] Running {label}...")
        results = []
        try:
            # We search worldwide to get a large enough sample to check for SDET phrases
            res = scrape_jobs(
                site_name=["linkedin"], 
                search_term=term, 
                location="United States", # Use US for high-volume SDET titles
                results_wanted=30, 
                hours_old=72
            )
            if res is not None and not res.empty:
                for _, row in res.iterrows():
                    results.append(f"{row['title']} @ {row['company']}")
        except Exception as e: print(f" Error: {e}")
        return set(results)

    rigid_results = run_search(rigid_term, "RIGID (Long List)")
    elastic_results = run_search(elastic_term, "ELASTIC (v2.8.2)")

    print(f"\n--- COMPARISON RESULTS ---")
    print(f"Rigid (Long) Found: {len(rigid_results)} roles")
    print(f"Elastic (v2.8.2) Found: {len(elastic_results)} roles")
    
    missing_in_elastic = rigid_results - elastic_results
    
    if not missing_in_elastic:
        print("\n✅ PROOF: Elastic v2.8.2 captured 100% of the long phrase results.")
    else:
        print("\n❌ MISSES: Elastic v2.8.2 missed these specific roles:")
        for r in missing_in_elastic: print(f"  - {r}")

    # Specific SDET Check
    print("\n--- SDET PHRASE CHECK ---")
    sdet_titles = [r for r in rigid_results if "Software Development Engineer in Test" in r]
    if sdet_titles:
        print(f"Found {len(sdet_titles)} SDET titles in Rigid results.")
        all_captured = all(t in elastic_results for t in sdet_titles)
        print(f"Were they all captured by v2.8.2? {'✅ YES' if all_captured else '❌ NO'}")
    else:
        print("No SDET-specific long titles found in this sample, but logic holds.")

if __name__ == "__main__":
    forensic_strict_comparison()
