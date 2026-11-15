"""Shared by the test_api_*.py files: a TestClient on the test database (the ``db``
fixture of conftest.py), a logged-in user, and small builders for rows.

A test file imports the fixtures it uses:
    from backend.tests.api_fixtures import admin, client, reviewer  # noqa: F401
"""
from datetime import datetime, timezone
from itertools import count

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_current_user
from backend.api.main import app
from backend.db.models import (AppUser, Company, JobPosting, JobRequirement, Lead,
                               LeadSnapshot, OutreachDraft, PipelineRun)
from backend.db.models.enums import (DraftStatus, ExtractionStatus, JobStatus, LeadStatus,
                                     RunStatus, Source, TriggerType, UserRole)
from backend.db.normalize import company_name_key, content_hash
from backend.db.session import get_db

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
TEXT = "Job description..."
_n = count(1)


# ---------- fixtures ----------

@pytest.fixture
def client(db):
    """Requests use the test session, so the test and the route see the same rows."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login_as(db, role: UserRole) -> AppUser:
    n = next(_n)
    # the database only checks that the hash looks like bcrypt; nobody logs in with it
    user = AppUser(full_name=f"Test {role.value}", email=f"{role.value}{n}@example.com",
                   password_hash="$2b$12$" + "x" * 53, role=role)
    db.add(user)
    db.flush()
    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture
def reviewer(db, client) -> AppUser:
    return _login_as(db, UserRole.REVIEWER)


@pytest.fixture
def admin(db, client) -> AppUser:
    return _login_as(db, UserRole.ADMIN)


# ---------- builders ----------

def make_company(db, name="Acme Corp", **fields) -> Company:
    company = Company(name=name, normalized_name=company_name_key(name), **fields)
    db.add(company)
    db.flush()
    return company


def make_job(db, company, title="Senior React Developer", fit_score=None, posted_at=NOW,
             status=None, **requirement) -> JobPosting:
    """A job. With ``fit_score`` (or requirement fields) it also gets its requirement row."""
    n = next(_n)
    if status is None:
        status = JobStatus.SCORED if fit_score is not None else JobStatus.DISCOVERED
    job = JobPosting(company=company, source=Source.HIMALAYAS, external_id=f"api-{n}",
                     url=f"https://himalayas.app/jobs/api-{n}", title=title,
                     description_text=TEXT, content_hash=content_hash(title, TEXT),
                     posted_at=posted_at, status=status)
    db.add(job)
    db.flush()
    if fit_score is not None or requirement:
        db.add(JobRequirement(
            job_posting=job, source_hash=job.content_hash, title=title,
            extraction_status=ExtractionStatus.OK, fit_score=fit_score,
            fit_reason=f"{title}: 3 profiles cover it" if fit_score is not None else None,
            **requirement))
        db.flush()
    return job


def make_lead(db, name="Acme Corp", scores=(92,), status=LeadStatus.QUALIFIED) -> Lead:
    """A company, one scored job per score, and its lead."""
    company = make_company(db, name)
    jobs = [make_job(db, company, title=f"React Developer {i}", fit_score=s)
            for i, s in enumerate(scores, start=1)]
    qualified = status != LeadStatus.NOT_QUALIFIED
    lead = Lead(company=company,
                lead_score=min(100, max(scores) + 5 * (len(scores) - 1)) if qualified else 0,
                best_job_score=max(scores) if qualified else 0,
                qualifying_jobs=len(jobs) if qualified else 0, status=status,
                reason=f"{name} has {len(jobs)} suitable role(s).",
                evidence={"job_ids": [j.job_id for j in jobs] if qualified else []},
                scored_at=NOW)
    db.add(lead)
    db.flush()
    return lead


def make_draft(db, lead, version=1, status=DraftStatus.PENDING_REVIEW,
               reviewed_by=None) -> OutreachDraft:
    draft = OutreachDraft(lead=lead, subject=f"Subject v{version}",
                          body=" ".join(["word"] * 150), word_count=150, version=version,
                          status=status, reviewed_by=reviewed_by,
                          reviewed_at=NOW if reviewed_by else None)
    db.add(draft)
    db.flush()
    return draft


def make_snapshot(db, lead, lead_score, created_at) -> LeadSnapshot:
    """The lead's numbers at one (finished) run."""
    run = PipelineRun(trigger_type=TriggerType.MANUAL, status=RunStatus.COMPLETED,
                      started_at=created_at)
    db.add(run)
    db.flush()
    snap = LeadSnapshot(lead=lead, run_id=run.run_id, lead_score=lead_score,
                        best_job_score=lead.best_job_score,
                        qualifying_jobs=lead.qualifying_jobs, status=lead.status,
                        created_at=created_at)
    db.add(snap)
    db.flush()
    return snap
