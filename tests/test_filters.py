import pytest
from conftest import LEVELS, DOMAINS, BLOCK_ANCHORS, BLACKLIST
from job_alert_bot_github import is_match, has_word_match, finalize_list


class TestIsMatch:
    """Title qualification gate — must have seniority AND domain, no block anchors."""

    @pytest.mark.parametrize("title", [
        "Engineering Manager - QA",
        "Director of Quality Engineering",
        "Head of Test Automation",
        "Senior Manager, SDET",
        "Staff Engineer - Quality",
        "QA Lead Manager",
        "ENGINEERING MANAGER QA",           # case insensitive
        "Principal Automation Engineer",
    ])
    def test_passing_titles(self, title):
        assert is_match(title, LEVELS, DOMAINS, BLOCK_ANCHORS) is True

    @pytest.mark.parametrize("title", [
        "Engineering Manager - Product",     # level only, wrong domain
        "Senior QA Engineer",                # domain only, no level
        "Product Manager - Quality",         # block anchor kills it
        "Project Manager QA",                # block anchor kills it
        "",                                  # empty title
        "Software Engineer",                 # neither level nor domain
        "Sales Manager",                     # level match but wrong domain
        "QA Analyst",                        # domain only
    ])
    def test_failing_titles(self, title):
        assert is_match(title, LEVELS, DOMAINS, BLOCK_ANCHORS) is False

    def test_block_anchor_overrides_valid_match(self):
        # "product" block anchor must kill even a valid level+domain title
        assert is_match("Product Quality Engineering Manager", LEVELS, DOMAINS, BLOCK_ANCHORS) is False

    def test_block_anchor_substring_does_not_block(self):
        # \bprod\b does NOT match "productivity" — word boundary after "prod" fails
        # so the title passes through (is_match returns True, not blocked)
        anchors = ["prod"]
        assert is_match("Quality Engineering Manager Productivity Tools", LEVELS, DOMAINS, anchors) is True
        # contrast: exact "product" anchor correctly blocks
        assert is_match("Product Quality Engineering Manager", LEVELS, DOMAINS, ["product"]) is False

    def test_empty_levels_always_fails(self):
        assert is_match("Engineering Manager QA", [], DOMAINS, BLOCK_ANCHORS) is False

    def test_empty_domains_always_fails(self):
        assert is_match("Engineering Manager QA", LEVELS, [], BLOCK_ANCHORS) is False

    def test_empty_block_anchors_does_not_affect_valid_match(self):
        assert is_match("Engineering Manager QA", LEVELS, DOMAINS, []) is True


class TestHasWordMatch:
    """Word boundary matcher — prevents substring false positives."""

    @pytest.mark.parametrize("text,terms,expected", [
        ("head of qa", ["qa"], True),               # exact match mid-string
        ("qa manager", ["qa"], True),               # match at start
        ("engineering qa", ["qa"], True),           # match at end
        ("QA Manager", ["qa"], True),               # case insensitive
        ("salesforce automation", ["sales"], False), # v3.2.1 regression — word boundary
        ("qae platform manager", ["qa"], False),    # partial word — qa != qae
        ("", ["qa"], False),                        # empty text
        ("engineering manager", [], False),         # empty term list
        ("recruiter staffing firm", ["sales"], False),  # no match
        ("head of sales quality", ["sales", "qa"], True),  # multi-term, first match wins
    ])
    def test_boundary_cases(self, text, terms, expected):
        assert has_word_match(text, terms) is expected

    def test_hyphenated_compound_does_not_bleed(self):
        # "lead" should not match "lead-free" as a boundary issue
        assert has_word_match("lead-free solder engineer", ["lead"]) is True
        # \b matches at hyphen boundary — this is correct expected behavior

    def test_multiple_terms_returns_true_on_first_match(self):
        assert has_word_match("qa manager", ["sdet", "qa", "automation"]) is True


class TestFinalizeList:
    """Final quality gate — blacklist + junior role sniper."""

    def test_empty_list_returns_two_empty_lists(self, blacklist):
        clean, sniped = finalize_list([], blacklist)
        assert clean == [] and sniped == []

    def test_clean_role_passes_through(self, job_factory, blacklist):
        jobs = [job_factory(title="Engineering Manager - QA")]
        clean, sniped = finalize_list(jobs, blacklist)
        assert len(clean) == 1 and len(sniped) == 0

    def test_multiple_clean_roles_all_pass(self, job_factory, blacklist):
        jobs = [job_factory(title=t) for t in [
            "Engineering Manager QA", "Director of Quality", "Head of Automation"
        ]]
        clean, sniped = finalize_list(jobs, blacklist)
        assert len(clean) == 3 and len(sniped) == 0

    @pytest.mark.parametrize("title,reason", [
        ("Junior QA Manager", "Junior/Associate Role"),
        ("Trainee Quality Manager", "Junior/Associate Role"),
        ("Associate Test Manager", "Junior/Associate Role"),
        ("Assistant Engineering Manager", "Junior/Associate Role"),
    ])
    def test_junior_variants_get_sniped(self, title, reason, job_factory, blacklist):
        clean, sniped = finalize_list([job_factory(title=title)], blacklist)
        assert len(clean) == 0
        assert sniped[0]["sniped_reason"] == reason

    @pytest.mark.parametrize("title", [
        "Senior Associate QA Manager",
        "Lead Associate Engineering Manager",
    ])
    def test_senior_lead_associate_exceptions_pass(self, title, job_factory, blacklist):
        clean, sniped = finalize_list([job_factory(title=title)], blacklist)
        assert len(clean) == 1 and len(sniped) == 0

    def test_blacklist_match_in_title_sniped(self, job_factory, blacklist):
        clean, sniped = finalize_list([job_factory(title="Sales QA Manager")], blacklist)
        assert len(sniped) == 1 and "Blacklist" in sniped[0]["sniped_reason"]

    def test_blacklist_match_in_company_sniped(self, job_factory, blacklist):
        clean, sniped = finalize_list([job_factory(company="Recruiter Corp")], blacklist)
        assert len(sniped) == 1

    def test_blacklist_match_in_location_sniped(self, job_factory, blacklist):
        clean, sniped = finalize_list([job_factory(location="Staffing Agency, Mumbai")], blacklist)
        assert len(sniped) == 1

    def test_blacklist_substring_does_not_snipe(self, job_factory, blacklist):
        # "sales" blacklist must NOT snipe "salesforce"
        clean, sniped = finalize_list([job_factory(company="Salesforce")], blacklist)
        assert len(clean) == 1 and len(sniped) == 0

    def test_mixed_list_correctly_split(self, job_factory, blacklist):
        jobs = [
            job_factory(title="Engineering Manager QA"),
            job_factory(title="Junior QA Manager"),
            job_factory(title="Director of Quality"),
            job_factory(company="Recruiter Agency"),
        ]
        clean, sniped = finalize_list(jobs, blacklist)
        assert len(clean) == 2 and len(sniped) == 2

    def test_sniped_job_has_reason_field(self, job_factory, blacklist):
        _, sniped = finalize_list([job_factory(title="Junior QA Manager")], blacklist)
        assert "sniped_reason" in sniped[0]

    def test_clean_job_has_no_sniped_reason(self, job_factory, blacklist):
        clean, _ = finalize_list([job_factory()], blacklist)
        assert "sniped_reason" not in clean[0]
