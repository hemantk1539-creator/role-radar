import pytest
import hashlib
from unittest.mock import patch, MagicMock
from conftest import LEVELS, DOMAINS, BLOCK_ANCHORS, JOB_SCHEMA_KEYS
from job_alert_bot_github import fetch_json, fetch_rss, fetch_ats, send_email


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


class TestEmailRendering:
    """send_email must build + escape the HTML digest without crashing.

    Regression guard: a local var named `html` inside send_email shadowed the `html` module,
    so the esc() closure called str.escape -> AttributeError on every email-with-jobs run.
    This was invisible because the deploy sanity restores history -> no new jobs -> early return.
    """

    @staticmethod
    def _fake_smtp(captured):
        class FakeSMTP:
            def __init__(self, *a, **k): pass
            def starttls(self): pass
            def login(self, *a, **k): pass
            def sendmail(self, frm, to, message): captured["msg"] = message
            def quit(self): pass
        return FakeSMTP

    @staticmethod
    def _cfg():
        return {"email": {"sender_email": "a@b.com", "app_password": "realpass-not-default",
                          "recipient_email": "a@b.com"},
                "search": {"india_tiers": {}, "global_tiers": {}}}

    def test_local_digest_builds_and_escapes(self, monkeypatch):
        captured = {}
        monkeypatch.setattr("job_alert_bot_github.smtplib.SMTP", self._fake_smtp(captured))
        jobs = [{"title": "R&D Quality Manager", "company": "Acme & Co",
                 "location": "pune [Signal: Remote-Local]", "site": "linkedin",
                 "job_url": "https://x/1?a=1&b=2", "signal": "x"}]
        assert send_email("Local Alert: 1 New City Roles", jobs, self._cfg()) is True
        assert "R&amp;D" in captured["msg"]        # title HTML-escaped
        assert "Acme &amp; Co" in captured["msg"]   # company HTML-escaped

    def test_global_digest_builds(self, monkeypatch):
        captured = {}
        monkeypatch.setattr("job_alert_bot_github.smtplib.SMTP", self._fake_smtp(captured))
        jobs = [{"title": "Senior Manager, QE", "company": "Globex",
                 "location": "remote", "site": "ats-globex", "job_url": "https://x/2", "signal": "ATS"}]
        assert send_email("Global Remote Alert: 1 New Global Remote Roles", jobs, self._cfg()) is True

    def test_empty_jobs_returns_false_without_send(self, monkeypatch):
        monkeypatch.setattr("job_alert_bot_github.smtplib.SMTP", self._fake_smtp({}))
        assert send_email("Local Alert: 0", [], self._cfg()) is False
