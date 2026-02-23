from jobspy import scrape_jobs

def current_test():
    print("--- CURRENT LOGIC AUDIT (v1.9.5) ---")
    term = '("Director Quality" OR "Director Software Quality" OR "Director of Test")'
    loc = "Bengaluru"
    rw = 50 
    ho = 72
    
    print(f"> Searching: '{term}' in '{loc}' (Depth: {rw}, Lookback: {ho}h)...")
    try:
        res = scrape_jobs( site_name=["linkedin"], search_term=term, location=loc, results_wanted=rw, hours_old=ho, country_indeed='india' )
        if res is not None and not res.empty:
            fluence = res[res['company'].str.contains('Fluence', case=False, na=False)]
            if not fluence.empty:
                print(f"\n[MATCH] CURRENT code FOUND IT! Total roles: {len(res)}")
            else:
                print(f"\n[FAIL] CURRENT code missed it. Found {len(res)} roles.")
        else:
            print("\n[ERROR] No results.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    current_test()
