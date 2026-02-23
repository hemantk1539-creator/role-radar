from jobspy import scrape_jobs

def exact_config_test():
    print("--- FORENSIC AUDIT: USER-PROVIDED STRINGS ---")
    term = '("Engineering Manager Quality" OR "Engineering Manager Test" OR "EM Automation" OR "Test Manager" OR "Director Quality" OR "Director of Test" OR "Head of Quality")'
    loc = "Bengaluru"
    rw = 50 
    ho = 72
    
    print(f"> Searching with EXACT provided string in '{loc}' (Depth: 50, Lookback: 72h)...")
    try:
        res = scrape_jobs( site_name=["linkedin"], search_term=term, location=loc, results_wanted=rw, hours_old=ho, country_indeed='india' )
        if res is not None and not res.empty:
            fluence = res[res['company'].str.contains('Fluence', case=False, na=False)]
            if not fluence.empty:
                print(f"\n[SUCCESS] FOUND IT! 'Director Quality' was enough.")
            else:
                print(f"\n[FAIL] MISSED. Role not found with provided string.")
        else:
            print("\n[ERROR] No results.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    exact_config_test()
