"""P2-3 fix: PATCH /jobs/{job_id}/requirements (FR-12). Real PostgreSQL (``db`` of
conftest.py). No LLM: a person corrects the extracted fields."""
import pytest

from backend.db.models.enums import ExtractionStatus, JobStatus
from backend.tests.api_fixtures import client, make_company, make_job, reviewer  # noqa: F401


def scored_job(db, **requirement):
    job = make_job(db, make_company(db), fit_score=72, required_skills=["react"],
                   min_years_experience=3, salary_min=4000, salary_max=6000, **requirement)
    return job


def url(job) -> str:
    return f"/jobs/{job.job_id}/requirements"


def test_edit_saves_the_sent_fields_and_the_job_is_scored_again(client, reviewer, db):
    job = scored_job(db)
    job.requirement.flag_reason = "No required skills found"
    job.requirement.extraction_status = ExtractionStatus.NEEDS_REVIEW
    db.flush()

    response = client.patch(url(job), json={"required_skills": ["React", " TypeScript "],
                                            "min_years_experience": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "parsed" and body["fit_score"] is None
    req = body["requirements"]
    assert req["required_skills"] == ["react", "typescript"]     # same rules as stage 2
    assert req["min_years_experience"] == 5
    assert (req["salary_min"], req["salary_max"]) == (4000, 6000)   # not sent: unchanged
    assert (req["fit_score"], req["fit_reason"], req["flag_reason"]) == (None, None, None)
    assert job.status == JobStatus.PARSED
    assert job.requirement.extraction_status == ExtractionStatus.OK


def test_a_field_can_be_cleared_with_null(client, reviewer, db):
    job = scored_job(db)

    body = client.patch(url(job), json={"min_years_experience": None}).json()

    assert body["requirements"]["min_years_experience"] is None


@pytest.mark.parametrize("sent", [
    {"min_years_experience": -3},
    {"min_years_experience": 51},
    {"salary_min": 9000},                        # above the saved salary_max (6000)
    {"salary_min": 7000, "salary_max": 5000},
    {"salary_currency": "DOLLARS"},
    {"timezone_offsets": [20]},
    {"seniority": "wizard"},
    {"fit_score": 99},                           # not a field a person can edit
])
def test_bad_values_are_422_and_change_nothing(client, reviewer, db, sent):
    job = scored_job(db)

    assert client.patch(url(job), json=sent).status_code == 422
    assert job.status == JobStatus.SCORED and job.requirement.fit_score == 72
    assert job.requirement.min_years_experience == 3


def test_a_discovered_job_has_nothing_to_edit(client, reviewer, db):
    job = make_job(db, make_company(db))                       # no requirements yet

    response = client.patch(url(job), json={"min_years_experience": 2})

    assert response.status_code == 404
    assert response.json() == {"detail": "This job has no extracted requirements yet"}


def test_unknown_job_is_404(client, reviewer, db):
    assert client.patch("/jobs/999999/requirements", json={}).status_code == 404
