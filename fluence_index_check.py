from jobspy import scrape_jobs

def fluence_index_check():
    print("--- FLUENCE INDEX AUDIT ---")
    try:
        res = scrape_jobs( site_name=["linkedin"], search_term="Fluence", location="Bengaluru", results_wanted=30, hours_old=168, country_indeed='india' )
        if res is not None and not res.empty:
            fluence = res[res['title'].str.contains('Quality', case=False, na=False)]
            if not fluence.empty:
                print(f"Role indexed as: {fluence.iloc[0]['title']}")
            else:
                print("Fluence found, but no Quality role indexed.")
        else:
            print("Fluence not searchable at all.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fluence_index_check()
