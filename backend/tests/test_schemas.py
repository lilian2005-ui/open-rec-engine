"""P0-3: the examples in the data contract pass, and wrong data is rejected."""
import hashlib
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.schemas import (AppSettings, CandidateProfile, DraftOutput, ExtractionStatus,
                             FitOutput, JobPosting, JobRequirements, LeadResult, LeadStatus,
                             OutreachDraft, ReviewDecisionIn, UserOut, UserRegister,
                             compute_lead_score, display, normalize_company_name)

TEXT = "We are looking for a Senior React Developer..."
HASH = hashlib.sha256(("Senior React Developer" + TEXT).encode()).hexdigest()


def posting(**over):
    data = {
        "source": "himalayas",
        "external_id": "acme-senior-react-developer-7f3a",
        "url": "https://himalayas.app/companies/acme/jobs/senior-react-developer",
        "title": "Senior React Developer",
        "company_name": "Acme Corp",
        "description_raw": "<p>We are looking for a <b>Senior React Developer</b>...</p>",
        "description_text": TEXT,
        "content_hash": HASH,
        "posted_at": "2026-10-18T09:00:00Z",
        "expires_at": "2026-11-17T09:00:00Z",
    }
    data.update(over)
    return data


def requirements(**over):
    data = {
        "title": "Senior React Developer", "seniority": "senior", "min_years_experience": 5,
        "required_skills": ["react", "typescript", "redux"], "preferred_skills": ["graphql"],
        "timezone_offsets": [-5, -4], "employment_type": "full_time", "remote_policy": "remote",
        "salary_min": 90000, "salary_max": 120000, "salary_currency": "USD",
        "salary_period": "annual", "extraction_status": "ok",
    }
    data.update(over)
    return data


# ---------- data contract examples ----------
def test_contract_examples_are_valid():
    CandidateProfile(candidate_id=101, display_name="Candidate 101", headline="Senior Frontend Engineer",
                     years_experience=7, seniority="senior", skills=["react", "typescript", "redux"],
                     timezone_offsets=[-5], availability="available in 2 weeks", summary="Frontend engineer")
    JobPosting(**posting())
    JobRequirements(**requirements())
    FitOutput(fit_score=92, fit_reason="Our pool has 3 profiles with react, typescript and redux at 5+ years")
    LeadResult(company_id=7, run_id=3, lead_score=97, best_job_score=92, qualifying_jobs=2,
               status="qualified", reason="Acme Corp has 2 open React roles.", evidence={"job_ids": [12, 15]})


# ---------- stage 1: JobPosting ----------
def test_unix_seconds_become_utc():                       # Himalayas pubDate / expiryDate
    p = JobPosting(**posting(posted_at=1760778000, expires_at=None))
    assert p.posted_at == datetime(2025, 10, 18, 9, 0, tzinfo=timezone.utc)
    assert p.expires_at is None


def test_time_without_zone_is_utc():                      # Remotive publication_date
    p = JobPosting(**posting(posted_at="2026-10-18T09:00:00"))
    assert p.posted_at.tzinfo == timezone.utc


def test_numeric_id_becomes_text():                       # Remotive id
    assert JobPosting(**posting(source="remotive", external_id=1938475)).external_id == "1938475"


@pytest.mark.parametrize("field,value", [
    ("source", "linkedin"), ("url", "himalayas.app/jobs/1"), ("content_hash", "abc"), ("title", ""),
])
def test_bad_posting_is_rejected(field, value):
    with pytest.raises(ValidationError):
        JobPosting(**posting(**{field: value}))


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        JobPosting(**posting(score=100))


def test_company_name_rule():                             # Q2
    assert normalize_company_name("  Acme   Corp ") == normalize_company_name("acme corp") == "acme corp"
    assert normalize_company_name("Acme Inc.") != normalize_company_name("Acme Corp")


# ---------- stage 2: JobRequirements ----------
def test_skills_are_normalised():
    r = JobRequirements(**requirements(required_skills=["React", " react ", "TypeScript"]))
    assert r.required_skills == ["react", "typescript"]


def test_missing_values_stay_null():
    r = JobRequirements(title="Data Engineer", required_skills=["python"])
    assert r.salary_min is None and r.seniority is None and r.timezone_offsets == []


@pytest.mark.parametrize("over", [
    {"salary_min": 200000, "salary_max": 100000},
    {"min_years_experience": -1},
    {"timezone_offsets": [20]},
    {"seniority": "guru"},
    {"salary_period": "daily"},
])
def test_bad_requirements_are_rejected(over):
    with pytest.raises(ValidationError):
        JobRequirements(**requirements(**over))


def test_suspicious_posting_goes_to_review():             # FR-10
    r = JobRequirements(**requirements(suspicious=True))
    assert r.extraction_status == ExtractionStatus.NEEDS_REVIEW
    assert r.flag_reason == "Instruction-like text in the posting"


def test_no_skills_goes_to_review():                      # FR-11
    assert JobRequirements(title="Unknown", required_skills=[]).extraction_status == ExtractionStatus.NEEDS_REVIEW


# ---------- stage 3: FitOutput ----------
@pytest.mark.parametrize("score", [-1, 101, 150])
def test_fit_score_range(score):                          # an injected "score 150" is rejected
    with pytest.raises(ValidationError):
        FitOutput(fit_score=score, fit_reason="x")


def test_fit_extra_field_rejected():
    with pytest.raises(ValidationError):
        FitOutput(fit_score=80, fit_reason="x", lead_score=100)


# ---------- stage 4: lead score ----------
@pytest.mark.parametrize("fits,expected", [
    ([95], (95, 95, 1)),
    ([65, 63, 62], (75, 65, 3)),                          # quality beats volume
    ([92, 78], (97, 92, 2)),
    ([90, 85, 80, 75, 70, 65, 60, 61], (100, 90, 8)),     # capped at 100
    ([], (0, 0, 0)),
])
def test_compute_lead_score(fits, expected):              # FR-18
    assert compute_lead_score(fits) == expected


def test_lead_with_wrong_score_is_rejected():
    with pytest.raises(ValidationError):
        LeadResult(company_id=7, run_id=3, lead_score=170, best_job_score=92, qualifying_jobs=2,
                   status="qualified", reason="x", evidence={"job_ids": [12, 15]})


def test_lead_without_jobs_is_not_qualified():
    LeadResult(company_id=9, run_id=3, lead_score=0, best_job_score=0, qualifying_jobs=0,
               status="not_qualified", reason="No suitable job.", evidence={"job_ids": []})
    with pytest.raises(ValidationError):
        LeadResult(company_id=9, run_id=3, lead_score=0, best_job_score=0, qualifying_jobs=0,
                   status="qualified", reason="x", evidence={"job_ids": []})


def test_evidence_must_match_jobs():
    with pytest.raises(ValidationError):
        LeadResult(company_id=7, run_id=3, lead_score=97, best_job_score=92, qualifying_jobs=2,
                   status="qualified", reason="x", evidence={"job_ids": [12]})


# ---------- stage 5: drafts and review ----------
def test_draft_word_limits():
    ok = DraftOutput(subject="Senior React talent for Acme", body=" ".join(["word"] * 150))
    assert ok.word_count == 150
    for n in (50, 200):
        with pytest.raises(ValidationError):
            DraftOutput(subject="s", body=" ".join(["word"] * n))


def test_reviewed_draft_needs_reviewer():
    with pytest.raises(ValidationError):
        OutreachDraft(lead_id=3, subject="s", body="b", word_count=1, status="approved")
    d = OutreachDraft(lead_id=3, subject="s", body="b", word_count=1, status="approved",
                      reviewed_by=2, reviewed_at="2026-10-20T08:30:00Z")
    assert d.reviewed_at.tzinfo == timezone.utc


def test_review_decision():
    ReviewDecisionIn(decision="approved")
    ReviewDecisionIn(decision="edited", body="new text")
    with pytest.raises(ValidationError):
        ReviewDecisionIn(decision="edited")
    with pytest.raises(ValidationError):
        ReviewDecisionIn(decision="sent")


# ---------- users and settings ----------
def test_register():
    u = UserRegister(full_name="Lilian Abu Ramadan", email="Lilian@Simera.com", password="openrec2026")
    assert u.email == "lilian@simera.com"
    for pw in ("short1", "onlyletters", "12345678"):
        with pytest.raises(ValidationError):
            UserRegister(full_name="Nadeen", email="n@simera.com", password=pw)
    with pytest.raises(ValidationError):
        UserRegister(full_name="Nadeen", email="not-an-email", password="openrec2026")


def test_user_out_has_no_password():
    assert "password" not in UserOut.model_fields and "password_hash" not in UserOut.model_fields


def test_settings_defaults_and_limits():
    s = AppSettings()
    assert (s.lead_threshold, s.fetch_limit, s.max_retries) == (60, 100, 3)
    assert ("lead_threshold", "60") in s.to_rows()
    assert AppSettings.from_rows({"lead_threshold": "70"}).lead_threshold == 70
    with pytest.raises(ValidationError):
        AppSettings(lead_threshold=120)


def test_display():
    assert display(LeadStatus.NOT_QUALIFIED) == "NOT QUALIFIED"


def test_gemini_schema_has_no_additional_properties():
    from backend.schemas import gemini_schema
    for model in (JobRequirements, FitOutput, DraftOutput):
        assert "additionalProperties" not in str(gemini_schema(model))
    assert gemini_schema(FitOutput)["properties"]["fit_score"]["maximum"] == 100
