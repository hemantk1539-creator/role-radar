import time
import pytest
from conftest import LEVELS, DOMAINS, BLOCK_ANCHORS, BLACKLIST
from job_alert_bot_github import finalize_list, has_word_match


class TestPerformance:
    """SLA assertions — filter logic must remain fast at pipeline scale."""

    def test_finalize_list_5000_jobs_under_2_seconds(self):
        jobs = [
            {"title": f"Engineering Manager QA {i}", "company": "Acme", "location": "Pune"}
            for i in range(5000)
        ]
        start = time.time()
        finalize_list(jobs, BLACKLIST)
        elapsed = time.time() - start
        assert elapsed < 2.0, f"finalize_list took {elapsed:.2f}s for 5000 jobs (limit: 2s)"

    def test_has_word_match_realistic_blacklist_under_1_second(self):
        # Realistic scale: ~50 terms (actual blacklist is ~47), 10000 iterations
        realistic_blacklist = [f"term{i}" for i in range(50)]
        start = time.time()
        for _ in range(10000):
            has_word_match("engineering manager qa automation", realistic_blacklist)
        elapsed = time.time() - start
        assert elapsed < 1.0, f"has_word_match x10000 took {elapsed:.2f}s (limit: 1s)"
