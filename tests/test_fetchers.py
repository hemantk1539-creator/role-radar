import pytest
from unittest.mock import patch, MagicMock
from conftest import LEVELS, DOMAINS, BLOCK_ANCHORS, JOB_SCHEMA_KEYS
from scrapers import fetch_json, fetch_rss, fetch_ats, SourceAudit


def mock_response(status=200, json_data=None):
    res = MagicMock()
    res.status_code = status
    res.json.return_value = json_data or {}
    return res


class TestFetchJson:
    """JSON API fetcher - parsing, filtering, error handling."""

    def test_happy_path_returns_matching_job(self):
        payload = {"jobs": [{"title": "Engineering Manager QA", "companyName": "Acme",
                              "location": "Remote", "applicationLink": "https://example.com/1",
                              "pubDate": "2026-05-18"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_json("TestHub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["title"] == "Engineering Manager QA"

    def test_non_matching_title_filtered_out(self):
        payload = {"jobs": [{"title": "Product Manager", "companyName": "Acme",
                              "location": "Remote", "applicationLink": "https://example.com/1"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_json("TestHub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_company_fallback_chain(self):
        # companyName → company_name → company → source
        payload = {"jobs": [{"title": "Engineering Manager QA", "company": "FallbackCo",
                              "location": "Remote", "url": "https://example.com/1"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_json("SourceName", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results[0]["company"] == "FallbackCo"

    def test_returns_empty_on_404(self):
        with patch("scrapers.requests.get", return_value=mock_response(status=404)):
            results = fetch_json("TestHub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_returns_empty_on_network_error(self):
        with patch("scrapers.requests.get", side_effect=Exception("Connection refused")):
            results = fetch_json("TestHub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_output_conforms_to_job_schema(self):
        payload = {"jobs": [{"title": "Engineering Manager QA", "companyName": "Acme",
                              "location": "Remote", "applicationLink": "https://example.com/1",
                              "pubDate": "2026-05-18"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_json("TestHub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert JOB_SCHEMA_KEYS.issubset(results[0].keys())


class TestFetchRss:
    """RSS feed fetcher - parsing, filtering, error handling."""

    def _make_feed(self, entries):
        feed = MagicMock()
        feed.entries = entries
        return feed

    def test_happy_path_returns_matching_job(self):
        entries = [{"title": "Engineering Manager QA", "author": "Acme",
                    "link": "https://example.com/1", "published": "2026-05-18"}]
        with patch("scrapers.feedparser.parse", return_value=self._make_feed(entries)):
            results = fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["title"] == "Engineering Manager QA"

    def test_non_matching_title_filtered_out(self):
        entries = [{"title": "Product Manager", "author": "Acme",
                    "link": "https://example.com/1", "published": "2026-05-18"}]
        with patch("scrapers.feedparser.parse", return_value=self._make_feed(entries)):
            results = fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_returns_empty_on_parse_exception(self):
        with patch("scrapers.feedparser.parse", side_effect=Exception("Parse error")):
            results = fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_output_conforms_to_job_schema(self):
        entries = [{"title": "Engineering Manager QA", "author": "Acme",
                    "link": "https://example.com/1", "published": "2026-05-18"}]
        with patch("scrapers.feedparser.parse", return_value=self._make_feed(entries)):
            results = fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert JOB_SCHEMA_KEYS.issubset(results[0].keys())


class TestFetchAts:
    """ATS platform fetcher - Greenhouse, Lever, Ashby schema parsing."""

    def test_greenhouse_extracts_absolute_url(self):
        payload = {"jobs": [{"title": "Engineering Manager QA",
                              "absolute_url": "https://boards.greenhouse.io/job/1"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["job_url"] == "https://boards.greenhouse.io/job/1"

    def test_lever_extracts_hosted_url_from_list(self):
        # Lever returns a list at root, uses "hostedUrl"
        payload = [{"text": "Engineering Manager QA", "hostedUrl": "https://jobs.lever.co/acme/1"}]
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("lever", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["job_url"] == "https://jobs.lever.co/acme/1"

    def test_ashby_extracts_job_url(self):
        payload = {"jobs": [{"title": "Engineering Manager QA",
                              "job_url": "https://jobs.ashbyhq.com/acme/1"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("ashby", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["job_url"] == "https://jobs.ashbyhq.com/acme/1"

    def test_non_matching_title_filtered_out(self):
        payload = {"jobs": [{"title": "Product Manager", "absolute_url": "https://example.com/1"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_returns_empty_on_500(self):
        with patch("scrapers.requests.get", return_value=mock_response(status=500)):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_returns_empty_on_network_error(self):
        with patch("scrapers.requests.get", side_effect=Exception("Timeout")):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_output_conforms_to_job_schema(self):
        payload = {"jobs": [{"title": "Engineering Manager QA",
                              "absolute_url": "https://boards.greenhouse.io/job/1"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert JOB_SCHEMA_KEYS.issubset(results[0].keys())


class TestSourceAudit:
    """Per-source outcome collector for the global burst (instrumentation)."""

    def test_records_ok_when_results_found(self):
        audit = SourceAudit()
        payload = {"jobs": [{"title": "Engineering Manager QA", "companyName": "Acme",
                             "location": "Remote", "applicationLink": "https://x/1", "pubDate": "2026-05-18"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            fetch_json("Hub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS, audit)
        ok, empty, error = audit.summary()
        assert ok == ["Hub"] and empty == [] and error == []

    def test_records_empty_when_reachable_but_zero_match(self):
        audit = SourceAudit()
        payload = {"jobs": [{"title": "Product Manager", "companyName": "Acme",
                             "location": "Remote", "applicationLink": "https://x/1"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            fetch_json("Hub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS, audit)
        ok, empty, error = audit.summary()
        assert empty == ["Hub"] and ok == [] and error == []

    def test_records_error_on_non_200(self):
        audit = SourceAudit()
        with patch("scrapers.requests.get", return_value=mock_response(status=500)):
            fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS, audit)
        ok, empty, error = audit.summary()
        assert error == ["greenhouse/acme"] and ok == [] and empty == []

    def test_records_error_on_exception(self):
        audit = SourceAudit()
        with patch("scrapers.requests.get", side_effect=Exception("Connection refused")):
            fetch_json("Hub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS, audit)
        ok, empty, error = audit.summary()
        assert error == ["Hub"]

    def test_rss_records_outcome(self):
        audit = SourceAudit()
        entries = [{"title": "Engineering Manager QA", "author": "Acme",
                    "link": "https://x/1", "published": "2026-05-18"}]
        feed = MagicMock()
        feed.entries = entries
        with patch("scrapers.feedparser.parse", return_value=feed):
            fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS, audit)
        ok, _, _ = audit.summary()
        assert ok == ["WWR"]

    def test_ats_label_is_unique_per_ats_type(self):
        # same token under two ATS types must not collide in the audit
        audit = SourceAudit()
        with patch("scrapers.requests.get", return_value=mock_response(status=500)):
            fetch_ats("greenhouse", "figma", LEVELS, DOMAINS, BLOCK_ANCHORS, audit)
            fetch_ats("lever", "figma", LEVELS, DOMAINS, BLOCK_ANCHORS, audit)
        _, _, error = audit.summary()
        assert error == ["greenhouse/figma", "lever/figma"]

    def test_omitting_audit_is_noop(self):
        # default None: behaviour identical to before, returns the list, no recording
        payload = {"jobs": [{"title": "Engineering Manager QA", "companyName": "Acme",
                             "location": "Remote", "applicationLink": "https://x/1", "pubDate": "2026-05-18"}]}
        with patch("scrapers.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_json("Hub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1 and results[0]["title"] == "Engineering Manager QA"
