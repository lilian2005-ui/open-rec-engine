"""P1-4: the fit service scores ``parsed`` jobs and saves the result.
Runs on real PostgreSQL (the ``db`` fixture rolls everything back after each test)."""
import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.db.models import Candidate, Company, JobPosting, JobRequirement
from backend.db.models.enums import ExtractionStatus, JobStatus, Seniority, Source
from backend.db.normalize import company_name_key, content_hash
from backend.fit.scorer import FakeFitScorer, FitScorer, GeminiFitScorer
from backend.fit.service import score_parsed_jobs

TEXT = "We are looking for a Senior React Developer..."


# ---------- builders ----------

def make_candidates(db, n=3):
    for i in range(n):
        db.add(Candidate(candidate_id=101 + i, display_name=f"Candidate {101 + i}",
                         skills=["react", "typescript"], years_experience=Decimal("6.5"),
                         seniority=Seniority.SENIOR, timezone_offsets=[-5]))
    db.flush()


def make_job(db, n, title="Senior React Developer", status=JobStatus.PARSED,
             with_requirement=True, fit_score=None):
    comp = db.scalar(select(Company).where(Company.normalized_name == "acme corp"))
    if comp is None:
        comp = Company(name="Acme Corp", normalized_name=company_name_key("Acme Corp"))
        db.add(comp)
        db.flush()
    job = JobPosting(
        company=comp, source=Source.HIMALAYAS, external_id=f"job-{n}",
        url=f"https://himalayas.app/jobs/{n}", title=title, description_text=TEXT,
        content_hash=content_hash(title, TEXT), status=status,
    )
    db.add(job)
    db.flush()
    if with_requirement:
        db.add(JobRequirement(
            job_posting=job, source_hash=job.content_hash, title=title, seniority=Seniority.SENIOR,
            min_years_experience=5, required_skills=["react", "typescript"],
            preferred_skills=[], timezone_offsets=[-5],
            extraction_status=ExtractionStatus.OK,
            fit_score=fit_score,
            fit_reason="Old reason" if fit_score is not None else None,
        ))
        db.flush()
    return job


class RecordingScorer(FakeFitScorer):
    """A fake scorer that remembers WHICH pool object it received."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.pool_ids = []

    def score(self, requirements, pool):
        self.pool_ids.append(id(pool))
        return super().score(requirements, pool)


class ExplodingScorer(FitScorer):
    """Fails for one title, works for the others."""

    def __init__(self, bad_title):
        self.bad_title = bad_title

    def score(self, requirements, pool):
        if requirements["title"] == self.bad_title:
            raise RuntimeError("boom")
        return FakeFitScorer(default_score=70).score(requirements, pool)


# ---------- tests ----------

def test_parsed_job_becomes_scored_with_score_and_reason(db):
    make_candidates(db)
    job = make_job(db, 1)

    result = score_parsed_jobs(db, FakeFitScorer(default_score=92))

    db.refresh(job)
    db.refresh(job.requirement)
    assert job.status == JobStatus.SCORED
    assert job.requirement.fit_score == 92
    assert job.requirement.fit_reason
    assert (result.scored, result.failed) == (1, 0)


def test_pool_is_read_once_and_sent_whole_for_every_job(db):
    make_candidates(db, n=3)
    make_job(db, 1, title="Job A")
    make_job(db, 2, title="Job B")
    scorer = RecordingScorer(default_score=80)

    score_parsed_jobs(db, scorer)

    assert [size for _, size in scorer.calls] == [3, 3]   # all 3 candidates each time
    assert len(set(scorer.pool_ids)) == 1                  # the same pool, read once


def test_ai_answer_of_150_is_rejected_and_job_is_unchanged(db):
    make_candidates(db)
    job = make_job(db, 1)
    too_high = GeminiFitScorer(lambda prompt, schema: json.dumps(
        {"fit_score": 150, "fit_reason": "great"}))

    result = score_parsed_jobs(db, too_high)

    db.refresh(job)
    db.refresh(job.requirement)
    assert job.status == JobStatus.PARSED            # still waiting, can be retried
    assert job.requirement.fit_score is None
    assert job.requirement.fit_reason is None
    assert (result.scored, result.failed) == (0, 1)


def test_needs_review_job_is_not_scored(db):
    make_candidates(db)
    job = make_job(db, 1, status=JobStatus.NEEDS_REVIEW)
    scorer = FakeFitScorer()

    result = score_parsed_jobs(db, scorer)

    db.refresh(job)
    db.refresh(job.requirement)
    assert job.status == JobStatus.NEEDS_REVIEW
    assert job.requirement.fit_score is None
    assert scorer.calls == []
    assert result.scored == 0


def test_already_scored_job_is_not_scored_again(db):
    make_candidates(db)
    job = make_job(db, 1, status=JobStatus.SCORED, fit_score=50)
    scorer = FakeFitScorer(default_score=99)

    score_parsed_jobs(db, scorer)

    db.refresh(job.requirement)
    assert job.requirement.fit_score == 50
    assert scorer.calls == []


def test_one_failing_job_does_not_stop_the_others(db):
    make_candidates(db)
    bad = make_job(db, 1, title="Bad job")
    good = make_job(db, 2, title="Good job")

    result = score_parsed_jobs(db, ExplodingScorer("Bad job"))

    db.refresh(bad)
    db.refresh(good)
    assert bad.status == JobStatus.PARSED
    assert good.status == JobStatus.SCORED
    assert (result.scored, result.failed) == (1, 1)
    assert "boom" in result.errors[0]


def test_parsed_job_without_requirements_is_reported_and_skipped(db):
    make_candidates(db)
    broken = make_job(db, 1, with_requirement=False)
    good = make_job(db, 2)

    result = score_parsed_jobs(db, FakeFitScorer())

    db.refresh(broken)
    db.refresh(good)
    assert broken.status == JobStatus.PARSED
    assert good.status == JobStatus.SCORED
    assert (result.scored, result.failed) == (1, 1)


def test_empty_candidate_table_stops_the_stage_with_a_clear_error(db):
    job = make_job(db, 1)

    with pytest.raises(RuntimeError, match="candidate table is empty"):
        score_parsed_jobs(db, FakeFitScorer())

    db.refresh(job)
    assert job.status == JobStatus.PARSED