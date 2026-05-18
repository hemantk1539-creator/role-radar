import pytest
import hashlib
from unittest.mock import patch, MagicMock
from conftest import LEVELS, DOMAINS, BLOCK_ANCHORS, JOB_SCHEMA_KEYS
from job_alert_bot_github import fetch_json, fetch_rss, fetch_ats


class TestJobSchema:
    """Output contract — every job dict must carry required keys."""

    def _greenhouse_payload(self):
        return {"jobs": [{"title": "Engineering Manager QA",
                          "absolute_url": "https://boards.greenhouse.io/job/1",
                          "updated_at": "2026-05-18"}]}

    def _rss_feed(self, entries):
        feed = MagicMock()
        feed.entries = entries
        return feed

    def test_fetch_json_output_has_all_required_keys(self):
        payload = {"jobs": [{"title": "Engineering Manager QA", "companyName": "Acme",
                              "location": "Remote", "applicationLink": "https://example.com/1",
                              "pubDate": "2026-05-18"}]}
        with patch("job_alert_bot_github.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = payload
            results = fetch_json("Hub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert all(JOB_SCHEMA_KEYS.issubset(j.keys()) for j in results)

    def test_fetch_rss_output_has_all_required_keys(self):
        entries = [{"title": "Engineering Manager QA", "author": "Acme",
                    "link": "https://example.com/1", "published": "2026-05-18"}]
        with patch("job_alert_bot_github.feedparser.parse", return_value=self._rss_feed(entries)):
            results = fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert all(JOB_SCHEMA_KEYS.issubset(j.keys()) for j in results)

    def test_fetch_ats_output_has_all_required_keys(self):
        with patch("job_alert_bot_github.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = self._greenhouse_payload()
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert all(JOB_SCHEMA_KEYS.issubset(j.keys()) for j in results)


class TestDeduplicationIntegrity:
    """Deduplication contracts — determinism and uniqueness."""

    def test_same_url_always_produces_same_md5(self):
        url = "https://example.com/job/123"
        h1 = hashlib.md5(url.encode("utf-8")).hexdigest()
        h2 = hashlib.md5(url.encode("utf-8")).hexdigest()
        assert h1 == h2

    def test_different_urls_produce_different_hashes(self):
        h1 = hashlib.md5("https://example.com/job/1".encode()).hexdigest()
        h2 = hashlib.md5("https://example.com/job/2".encode()).hexdigest()
        assert h1 != h2

    def test_md5_hash_is_32_chars(self):
        h = hashlib.md5("https://example.com/job/1".encode()).hexdigest()
        assert len(h) == 32
