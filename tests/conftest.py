import pytest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Shared Constants ---
LEVELS = ["manager", "director", "head", "engineering manager", "em", "staff", "lead", "principal"]
DOMAINS = ["qa", "quality", "test", "automation", "sdet", "qe"]
BLOCK_ANCHORS = ["product", "project manager"]
BLACKLIST = ["sales", "recruiter", "staffing", "vendor"]
REMOTE_SIGNALS = ["remote", "wfh", "work from home", "telecommute"]
GLOBAL_REMOTE_SIGNALS = ["timezone agnostic", "planet-scale", "fully remote", "distributed"]
HYBRID_SIGNALS = ["hybrid", "flexible", "flex", "partially", "office optional", "wfo"]
INDIA_WFH_TERMS = ["remote", "wfh", "work from home", "telecommute", "pan india"]
RESIDENCY_SIGNALS = ["us citizen", "security clearance", "w2 only", "must reside in the us"]
INDIA_CITY_ALIASES = ["pune", "bengaluru", "bangalore", "gurugram", "mumbai", "delhi", "hyderabad"]
INDIA_CODE = "in"
GLOBAL_LOC = "Remote"

JOB_SCHEMA_KEYS = {"title", "company", "location", "signal", "job_url", "site", "date"}


@pytest.fixture
def levels():
    return LEVELS

@pytest.fixture
def domains():
    return DOMAINS

@pytest.fixture
def block_anchors():
    return BLOCK_ANCHORS

@pytest.fixture
def blacklist():
    return BLACKLIST

@pytest.fixture
def remote_signals():
    return REMOTE_SIGNALS

@pytest.fixture
def global_remote_signals():
    return GLOBAL_REMOTE_SIGNALS

@pytest.fixture
def residency_signals():
    return RESIDENCY_SIGNALS

@pytest.fixture
def india_city_aliases():
    return INDIA_CITY_ALIASES

@pytest.fixture
def job_factory():
    def _make(title="Engineering Manager - QA", company="Acme Corp",
               location="Pune, India", job_url="https://example.com/job/1"):
        return {"title": title, "company": company, "location": location, "job_url": job_url}
    return _make

@pytest.fixture
def history_file(tmp_path):
    return str(tmp_path / "job_history.json")

@pytest.fixture
def save_config():
    return {"search": {"max_history": 2000}}
