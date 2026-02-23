import yaml
import os
from jobspy import scrape_jobs

def sat_test():
    print("--- SATURDAY FORENSIC AUDIT ---")
    try:
        # PowerShell redirect often creates UTF-16 LE
        with open("config_sat.yaml", "r", encoding="utf-16") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error reading config_sat.yaml: {e}")
        return
    
    # These were the Saturday night parameters
    term = '("Director Quality" OR "Director QA" OR "QE Director")'
    loc = "Bengaluru"
    rw = 40 # Saturday's limit
    ho = 48 # Saturday's lookback
    
    print(f"> Searching: '{term}' in '{loc}' (Depth: {rw}, Lookback: {ho}h)...")
    try:
        res = scrape_jobs(
            site_name=["linkedin"],
            search_term=term,
            location=loc,
            results_wanted=rw,
            hours_old=ho,
            country_indeed='india'
        )
        
        if res is not None and not res.empty:
            fluence = res[res['company'].str.contains('Fluence', case=False, na=False)]
            if not fluence.empty:
                print("\n[MATCH] Saturday code WOULD HAVE found it!")
            else:
                print(f"\n[FAIL] Saturday code MISSED it. Found {len(res)} roles.")
                for index, row in res.head(5).iterrows():
                    print(f" - {row['title']} at {row['company']}")
        else:
            print("\n[ERROR] No results.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    sat_test()
