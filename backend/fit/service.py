"""Stage 3 service (P1-4): scores every ``parsed`` job and saves the result.

Reads the candidate pool ONCE per run, asks the scorer for one fit score per job,
and saves ``fit_score`` + ``fit_reason`` on ``job_requirement`` and moves the job to
``scored``. Everything goes through the ORM (no hand-written SQL).
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from backend.db.models import Candidate, JobPosting
from backend.db.models.enums import JobStatus
from backend.fit.scorer import CANDIDATE_FIELDS, REQUIREMENT_FIELDS, FitScorer

log = logging.getLogger(__name__)


@dataclass
class FitRunResult:
    """What happened in one run of this stage (for the run log)."""

    scored: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.errors)


def _plain(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """Copy some fields of an ORM object into a plain dict (enums become strings)."""
    data = {}
    for name in fields:
        value = getattr(obj, name)
        data[name] = value.value if isinstance(value, Enum) else value
    return data


def load_pool(db: Session) -> list[dict[str, Any]]:
    """The mock candidates, read once. Ordered by id so the prompt is stable."""
    candidates = db.scalars(select(Candidate).order_by(Candidate.candidate_id)).all()
    return [_plain(c, CANDIDATE_FIELDS) for c in candidates]


def score_parsed_jobs(db: Session, scorer: FitScorer) -> FitRunResult:
    """Score every job whose status is ``parsed``.

    - ``needs_review`` jobs are not touched: they wait for a person.
    - If the scorer fails or answers with an invalid value (for example score 150),
      the job is left unchanged (still ``parsed``), the error is recorded, and the
      other jobs continue (FR-29).
    """
    pool = load_pool(db)
    if not pool:
        raise RuntimeError(
            "The candidate table is empty. Load the mock candidates first "
            "with the seed script (backend/db/seed_candidates.py)."
        )

    jobs = db.scalars(
        select(JobPosting)
        .where(JobPosting.status == JobStatus.PARSED)
        .options(selectinload(JobPosting.requirement))
        .order_by(JobPosting.job_id)
    ).all()

    result = FitRunResult()
    for job in jobs:
        req = job.requirement
        if req is None:
            msg = f"job {job.job_id}: status is parsed but it has no requirements"
            log.error(msg)
            result.errors.append(msg)
            continue

        try:
            out = scorer.score(_plain(req, REQUIREMENT_FIELDS), pool)
        except Exception as exc:  # one bad job must never stop the others
            msg = f"job {job.job_id}: scoring failed: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue

        try:
            # the database requires score and reason together (fit_score_has_reason)
            req.fit_score = out.fit_score
            req.fit_reason = out.fit_reason
            job.status = JobStatus.SCORED
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            msg = f"job {job.job_id}: could not save the score: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue

        result.scored += 1

    return result