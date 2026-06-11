import pytest
from conftest import (REMOTE_SIGNALS, GLOBAL_REMOTE_SIGNALS, RESIDENCY_SIGNALS,
                      INDIA_CITY_ALIASES, INDIA_CODE, GLOBAL_LOC, HYBRID_SIGNALS, INDIA_WFH_TERMS)
from filters import categorize_job


def categorize(title="", loc="", country=INDIA_CODE):
    return categorize_job(
        title, loc, country, INDIA_CODE, GLOBAL_LOC,
        REMOTE_SIGNALS, GLOBAL_REMOTE_SIGNALS, INDIA_CITY_ALIASES, RESIDENCY_SIGNALS,
        HYBRID_SIGNALS, INDIA_WFH_TERMS
    )


class TestCategorizeJob:
    """3-bucket routing - local, india_remote, global_remote, and drop cases."""

    def test_india_city_with_remote_goes_to_local(self):
        bucket, signal = categorize(loc="pune remote")
        assert bucket == "local"

    def test_india_city_without_remote_goes_to_local(self):
        bucket, signal = categorize(loc="pune, india")
        assert bucket == "local"

    def test_india_wfh_goes_to_india_remote(self):
        bucket, signal = categorize(loc="remote", country=INDIA_CODE)
        assert bucket == "india_remote"
        assert signal == "India-WFA"

    def test_hybrid_signal_in_city_gets_local_bucket(self):
        # hybrid without explicit remote signal → local bucket, signal is None
        bucket, signal = categorize(loc="pune hybrid")
        assert bucket == "local"
        assert signal is None

    def test_global_signal_in_india_goes_to_global_remote(self):
        bucket, signal = categorize(loc="pune remote timezone agnostic")
        assert bucket == "global_remote"
        assert signal == "Global-In-India"

    def test_worldwide_country_code_goes_to_global_remote(self):
        bucket, signal = categorize(loc="remote", country="worldwide")
        assert bucket == "global_remote"
        assert signal == "Worldwide Task"

    def test_global_signal_non_india_goes_to_global_remote(self):
        bucket, signal = categorize(loc="remote fully remote", country="us")
        assert bucket == "global_remote"

    def test_residency_signal_drops_job(self):
        bucket, signal = categorize(loc="remote", title="must reside in the us")
        assert bucket is None and signal is None

    def test_residency_signal_in_location_drops_job(self):
        bucket, signal = categorize(loc="remote us citizen only")
        assert bucket is None and signal is None

    def test_no_signal_no_city_returns_none(self):
        bucket, signal = categorize(loc="singapore", country="sg")
        assert bucket is None

    def test_pan_india_without_remote_signal_goes_to_local(self):
        # "pan india" matches a city alias but has no remote signal → local bucket
        bucket, signal = categorize(loc="pan india", country=INDIA_CODE)
        assert bucket == "local"

    def test_wfh_goes_to_india_remote(self):
        bucket, signal = categorize(loc="wfh", country=INDIA_CODE)
        assert bucket == "india_remote"
