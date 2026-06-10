import pytest
from unittest.mock import patch, MagicMock
from conftest import LEVELS, DOMAINS, BLOCK_ANCHORS, JOB_SCHEMA_KEYS
from job_alert_bot_github import fetch_json, fetch_rss, fetch_ats


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
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_json("TestHub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["title"] == "Engineering Manager QA"

    def test_non_matching_title_filtered_out(self):
        payload = {"jobs": [{"title": "Product Manager", "companyName": "Acme",
                              "location": "Remote", "applicationLink": "https://example.com/1"}]}
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_json("TestHub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_company_fallback_chain(self):
        # companyName → company_name → company → source
        payload = {"jobs": [{"title": "Engineering Manager QA", "company": "FallbackCo",
                              "location": "Remote", "url": "https://example.com/1"}]}
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_json("SourceName", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results[0]["company"] == "FallbackCo"

    def test_returns_empty_on_404(self):
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(status=404)):
            results = fetch_json("TestHub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_returns_empty_on_network_error(self):
        with patch("job_alert_bot_github.requests.get", side_effect=Exception("Connection refused")):
            results = fetch_json("TestHub", "https://api.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_output_conforms_to_job_schema(self):
        payload = {"jobs": [{"title": "Engineering Manager QA", "companyName": "Acme",
                              "location": "Remote", "applicationLink": "https://example.com/1",
                              "pubDate": "2026-05-18"}]}
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(json_data=payload)):
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
        with patch("job_alert_bot_github.feedparser.parse", return_value=self._make_feed(entries)):
            results = fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["title"] == "Engineering Manager QA"

    def test_non_matching_title_filtered_out(self):
        entries = [{"title": "Product Manager", "author": "Acme",
                    "link": "https://example.com/1", "published": "2026-05-18"}]
        with patch("job_alert_bot_github.feedparser.parse", return_value=self._make_feed(entries)):
            results = fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_returns_empty_on_parse_exception(self):
        with patch("job_alert_bot_github.feedparser.parse", side_effect=Exception("Parse error")):
            results = fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_output_conforms_to_job_schema(self):
        entries = [{"title": "Engineering Manager QA", "author": "Acme",
                    "link": "https://example.com/1", "published": "2026-05-18"}]
        with patch("job_alert_bot_github.feedparser.parse", return_value=self._make_feed(entries)):
            results = fetch_rss("WWR", "https://rss.test.com", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert JOB_SCHEMA_KEYS.issubset(results[0].keys())


class TestFetchAts:
    """ATS platform fetcher - Greenhouse, Lever, Ashby schema parsing."""

    def test_greenhouse_extracts_absolute_url(self):
        payload = {"jobs": [{"title": "Engineering Manager QA",
                              "absolute_url": "https://boards.greenhouse.io/job/1"}]}
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["job_url"] == "https://boards.greenhouse.io/job/1"

    def test_lever_extracts_hosted_url_from_list(self):
        # Lever returns a list at root, uses "hostedUrl"
        payload = [{"text": "Engineering Manager QA", "hostedUrl": "https://jobs.lever.co/acme/1"}]
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("lever", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["job_url"] == "https://jobs.lever.co/acme/1"

    def test_ashby_extracts_job_url(self):
        payload = {"jobs": [{"title": "Engineering Manager QA",
                              "job_url": "https://jobs.ashbyhq.com/acme/1"}]}
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("ashby", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert len(results) == 1
        assert results[0]["job_url"] == "https://jobs.ashbyhq.com/acme/1"

    def test_non_matching_title_filtered_out(self):
        payload = {"jobs": [{"title": "Product Manager", "absolute_url": "https://example.com/1"}]}
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_returns_empty_on_500(self):
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(status=500)):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_returns_empty_on_network_error(self):
        with patch("job_alert_bot_github.requests.get", side_effect=Exception("Timeout")):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert results == []

    def test_output_conforms_to_job_schema(self):
        payload = {"jobs": [{"title": "Engineering Manager QA",
                              "absolute_url": "https://boards.greenhouse.io/job/1"}]}
        with patch("job_alert_bot_github.requests.get", return_value=mock_response(json_data=payload)):
            results = fetch_ats("greenhouse", "acme", LEVELS, DOMAINS, BLOCK_ANCHORS)
        assert JOB_SCHEMA_KEYS.issubset(results[0].keys())
