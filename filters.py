"""
filters.py - pure title/location qualification logic.

Every function here is deterministic and side-effect-free (the requirement behind the
"all business logic at module level / testable" decision). Word-boundary regex (\b) is
used everywhere to prevent substring false positives (e.g. "sales" must not match
"salesforce", "associate" must not match "associated").
"""
import re


def is_match(title, levels, domains, block_anchors):
    t = title.lower()
    has_level = any(re.search(r'\b' + re.escape(l) + r'\b', t, re.IGNORECASE) for l in levels)
    has_domain = any(re.search(r'\b' + re.escape(d) + r'\b', t, re.IGNORECASE) for d in domains)
    is_blocked = any(re.search(r'\b' + re.escape(b) + r'\b', t, re.IGNORECASE) for b in block_anchors)
    return has_level and has_domain and not is_blocked


def has_word_match(text, term_list):
    for term in term_list:
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def india_is_applicable(title_str, loc_str, levels, domains, blacklist, block_anchors=()):
    """India-side applicability gate (pure, unit-tested).

    Mirrors the global is_match() contract for the India pipeline, which previously
    duplicated this logic inline inside run(). Returns True to KEEP a role, False to DROP.

      A.  blacklist hit on title OR location          -> drop
      B.  needs a seniority word AND a domain word     -> else drop
      B2. negative-domain block_anchors hit on title   -> drop
          (defaults to empty = NO-OP; populated in a later step for noise filtering)

    Inputs are expected pre-lowercased by the caller; has_word_match is case-insensitive anyway.
    """
    # A. HUB-APPLICABILITY GUARD
    if has_word_match(title_str, blacklist) or has_word_match(loc_str, blacklist):
        return False
    # B. SENIORITY + DOMAIN WHITELIST (strict word boundaries)
    if not (has_word_match(title_str, levels) and has_word_match(title_str, domains)):
        return False
    # B2. NEGATIVE-DOMAIN BLOCK ANCHORS (no-op until populated in Step 2)
    if block_anchors and has_word_match(title_str, block_anchors):
        return False
    return True


def finalize_list(job_list, blacklist):
    clean_list = []
    sniped_list = []
    for j in job_list:
        t = str(j.get('title', '')).lower()
        c = str(j.get('company', '')).lower()
        l = str(j.get('location', '')).lower()
        reason = None
        for b in blacklist:
            pattern = r'\b' + re.escape(b) + r'\b'
            if re.search(pattern, t) or re.search(pattern, l) or re.search(pattern, c):
                reason = f"Blacklist: {b}"
                break
        if not reason:
            # Word-boundary (\b) matching - NOT substring - so "associate" never trips on "associated".
            if has_word_match(t, ["assistant", "junior", "trainee", "associate"]):
                if not has_word_match(t, ["senior associate", "lead associate"]):
                    reason = "Junior/Associate Role"
        if reason:
            j['sniped_reason'] = reason
            sniped_list.append(j)
        else:
            clean_list.append(j)
    return clean_list, sniped_list


def categorize_job(title_str, loc_str, country_code, india_code, global_loc,
                   remote_signals, global_remote_signals, india_city_aliases, residency_signals,
                   hybrid_signals, india_wfh_terms):
    """Routes a job to a bucket. Returns (bucket, signal) or (None, None) to drop."""
    if any(rs in title_str or rs in loc_str for rs in residency_signals):
        return None, None
    has_global_signal = any(gs in title_str or gs in loc_str for gs in global_remote_signals)
    is_remote_explicit = any(r in loc_str or r in title_str for r in remote_signals)
    is_local_city = any(city in loc_str for city in india_city_aliases if city not in [global_loc.lower(), 'remote'])
    is_hybrid_signal = any(h in loc_str or h in title_str for h in hybrid_signals)
    is_india_job = ("india" in loc_str or is_local_city) or \
                   (country_code == india_code and loc_str.strip() in india_wfh_terms)
    if is_remote_explicit:
        if country_code == india_code:
            if has_global_signal:
                return "global_remote", "Global-In-India"
            elif is_local_city:
                return "local", f"{'Hybrid' if is_hybrid_signal else 'Remote'}-Local"
            elif is_india_job:
                return "india_remote", "India-WFA"
        elif country_code == "worldwide":
            return "global_remote", "Worldwide Task"
        elif has_global_signal:
            sig = next((s for s in global_remote_signals if s in title_str or s in loc_str), "Global")
            return "global_remote", sig
    elif is_local_city:
        return "local", None
    elif country_code == india_code and is_india_job:
        return "local", None
    return None, None
