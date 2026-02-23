from jobspy import scrape_jobs

def intersection_test():
    print("--- INTERSECTION LOGIC TEST ---")
    # Using Boolean Intersection instead of a Phrase
    term = '(Director AND Quality)'
    loc = "Bengaluru"
    
    print(f"> Searching: '{term}' in '{loc}'...")
    try:
        res = scrape_jobs( site_name=["linkedin"], search_term=term, location=loc, results_wanted=30, hours_old=168, country_indeed='india' )
        if res is not None and not res.empty:
            fluence = res[res['company'].str.contains('Fluence', case=False, na=False)]
            if not fluence.empty:
                print(f"
[SUCCESS] Intersection found it! Role: {fluence.iloc[0]['title']}")
            else:
                print("
[FAIL] Intersection missed it. Showing latest titles:")
                print(res[['title', 'company']].head(5))
        else:
            print("
[ERROR] No results.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    intersection_test()
