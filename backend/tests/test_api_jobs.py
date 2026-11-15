"""P2-3: GET /jobs and GET /jobs/{job_id}. Real PostgreSQL (``db`` of conftest.py)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.db.models import PipelineRun
from backend.db.models.enums import (EmploymentType, JobStatus, RemotePolicy, RunStatus,
                                     SalaryPeriod, Seniority, TriggerType)
from backend.db.normalize import content_hash
from backend.discovery.service import upsert_job
from backend.schemas.job import JobPosting as JobPostingIn
from backend.tests.api_fixtures import (NOW, TEXT, client, make_company, make_job,  # noqa: F401
                                        reviewer)

POSTED = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)


def titles(response) -> list[str]:
    return [item["title"] for item in response.json()["items"]]


# ---------- list ----------

def test_list_has_the_contract_shape(client, reviewer, db):
    job = make_job(db, make_company(db, "Acme Corp"), fit_score=92, posted_at=POSTED)

    response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json() == {
        "items": [{
            "job_id": job.job_id,
            "title": "Senior React Developer",
            "company_name": "Acme Corp",
            "source": "himalayas",
            "posted_at": "2026-11-07T10:00:00Z",
            "status": "scored",
            "fit_score": 92,
        }],
        "total": 1, "page": 1, "page_size": 20,
    }


def test_a_job_that_is_not_scored_has_no_fit_score(client, reviewer, db):
    make_job(db, make_company(db))

    [item] = client.get("/jobs").json()["items"]

    assert item["status"] == "discovered"
    assert item["fit_score"] is None


def test_newest_first_and_no_date_last(client, reviewer, db):
    acme = make_company(db)
    make_job(db, acme, title="Old", posted_at=NOW - timedelta(days=5))
    make_job(db, acme, title="No date", posted_at=None)
    make_job(db, acme, title="New", posted_at=NOW)

    assert titles(client.get("/jobs")) == ["New", "Old", "No date"]


def test_q_searches_title_or_company_without_case(client, reviewer, db):
    make_job(db, make_company(db, "Acme Corp"), title="React Developer")
    make_job(db, make_company(db, "Globex"), title="Python Developer")
    make_job(db, make_company(db, "Initech"), title="Engineer for ACME systems")

    response = client.get("/jobs", params={"q": "acme"})

    assert sorted(titles(response)) == ["Engineer for ACME systems", "React Developer"]
    assert response.json()["total"] == 2


def test_q_is_text_not_a_pattern(client, reviewer, db):
    make_job(db, make_company(db), title="React Developer")

    assert titles(client.get("/jobs", params={"q": "%"})) == []
    assert titles(client.get("/jobs", params={"q": "_eact"})) == []


def test_status_filter(client, reviewer, db):
    acme = make_company(db)
    make_job(db, acme, title="Scored", fit_score=80)
    make_job(db, acme, title="Discovered")
    make_job(db, acme, title="Failed", status=JobStatus.FAILED)

    assert titles(client.get("/jobs", params={"status": "scored"})) == ["Scored"]
    assert client.get("/jobs", params={"status": "nonsense"}).status_code == 422


def test_pages(client, reviewer, db):
    acme = make_company(db)
    for day in range(3):
        make_job(db, acme, title=f"Job {day}", posted_at=NOW - timedelta(days=day))

    body = client.get("/jobs", params={"page": 2, "page_size": 2}).json()

    assert [i["title"] for i in body["items"]] == ["Job 2"]
    assert (body["total"], body["page"], body["page_size"]) == (3, 2, 2)


def test_page_limits(client, reviewer, db):
    assert client.get("/jobs", params={"page_size": 100}).status_code == 200
    assert client.get("/jobs", params={"page_size": 101}).status_code == 422
    assert client.get("/jobs", params={"page": 0}).status_code == 422


# ---------- one job ----------

def test_detail_has_the_contract_shape(client, reviewer, db):
    job = make_job(
        db, make_company(db, "Acme Corp"), fit_score=92, posted_at=POSTED,
        required_skills=["react", "typescript"], preferred_skills=["redux"],
        seniority=Seniority.SENIOR, min_years_experience=5, timezone_offsets=[-5, -4],
        employment_type=EmploymentType.FULL_TIME, remote_policy=RemotePolicy.REMOTE,
        salary_min=Decimal("90000"), salary_max=Decimal("120000.50"), salary_currency="USD",
        salary_period=SalaryPeriod.ANNUAL)

    response = client.get(f"/jobs/{job.job_id}")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": job.job_id,
        "title": "Senior React Developer",
        "company_name": "Acme Corp",
        "source": "himalayas",
        "posted_at": "2026-11-07T10:00:00Z",
        "status": "scored",
        "fit_score": 92,
        "url": job.url,
        "description_text": TEXT,
        "expires_at": None,
        "requirements": {
            "required_skills": ["react", "typescript"],
            "preferred_skills": ["redux"],
            "seniority": "senior",
            "min_years_experience": 5,
            "timezone_offsets": [-5, -4],
            "employment_type": "full_time",
            "remote_policy": "remote",
            "salary_min": 90000,
            "salary_max": 120000.5,
            "salary_currency": "USD",
            "salary_period": "annual",
            "fit_score": 92,
            "fit_reason": "Senior React Developer: 3 profiles cover it",
            "flag_reason": None,
        },
    }


def test_detail_of_a_discovered_job_has_no_requirements(client, reviewer, db):
    job = make_job(db, make_company(db))

    body = client.get(f"/jobs/{job.job_id}").json()

    assert body["requirements"] is None
    assert body["fit_score"] is None


def test_a_posting_that_changed_hides_its_old_requirements(client, reviewer, db):
    """Q1: a changed posting goes back to discovered but keeps its old requirement
    row. The API must not show that old fit score or those old requirements."""
    company = make_company(db, "Acme Corp")
    job = make_job(db, company, fit_score=92, required_skills=["react"])
    run = PipelineRun(trigger_type=TriggerType.MANUAL, status=RunStatus.RUNNING, started_at=NOW)
    db.add(run)
    db.flush()
    new_text = "The same role, with a new description."
    changed = JobPostingIn(source=job.source, external_id=job.external_id, url=job.url,
                           title=job.title, company_name=company.name,
                           description_text=new_text,
                           content_hash=content_hash(job.title, new_text))

    assert upsert_job(db, changed, company.company_id, run.run_id) == "updated"
    assert job.status == JobStatus.DISCOVERED
    assert job.requirement.fit_score == 92             # the old row is still in the database

    [item] = client.get("/jobs").json()["items"]
    assert (item["status"], item["fit_score"]) == ("discovered", None)
    detail = client.get(f"/jobs/{job.job_id}").json()
    assert (detail["fit_score"], detail["requirements"]) == (None, None)
    assert detail["description_text"] == new_text


def test_unknown_job_is_404(client, reviewer, db):
    response = client.get("/jobs/999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}
