"""Stage 2 (P1-3): turn every `discovered` job into structured requirements.

For each job: build the prompt, ask the LLM, put the source values on top (A1),
check for injection, then save one job_requirement row and set the job status:
- parsed        everything is fine, the job goes on to fit scoring (P1-4)
- needs_review  missing title or skills, or the posting looks like an attack
- failed        the LLM gave no valid answer after the retries
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import JobPosting, JobRequirement
from backend.llm import LLMError, call_llm, generate
from backend.schemas.enums import ExtractionStatus, JobStatus
from backend.schemas.job import JobRequirements
from backend.understanding.prompt import build_prompt
from backend.understanding.source import apply_source_fields

log = logging.getLogger(__name__)

# FR-10: instruction-like text, checked by code as well as by the LLM
SUSPICIOUS = re.compile(
    r"ignore (all |the )?(previous|above|prior) instructions|you are now|system prompt|"
    r"give (this|the) job (a )?(score|100)",
    re.IGNORECASE,
)
INJECTION_REASON = "Instruction-like text in the posting"


@dataclass
class UnderstandingResult:
    parsed: int = 0
    needs_review: int = 0
    failed: int = 0
    errors: list[dict] = field(default_factory=list)   # for pipeline_run.errors (P1-6)


def understand_jobs(db: Session, *, call=call_llm, max_retries: int = 3) -> UnderstandingResult:
    """Process every `discovered` job. One job failing never stops the others."""
    result = UnderstandingResult()
    jobs = db.scalars(
        select(JobPosting).where(JobPosting.status == JobStatus.DISCOVERED).order_by(JobPosting.job_id)
    ).all()
    for job in jobs:
        try:
            status = understand_one(db, job, call=call, max_retries=max_retries)
        except LLMError as exc:
            # Q1: the old requirement (if any) is kept; only a successful run replaces it
            job.status = JobStatus.FAILED
            status = JobStatus.FAILED
            result.errors.append({"stage": "understanding", "job_id": job.job_id,
                                  "attempts": exc.attempts, "message": str(exc)})
            log.warning("job %s failed: %s", job.job_id, exc)
        db.commit()                                     # one job at a time
        if status == JobStatus.PARSED:
            result.parsed += 1
        elif status == JobStatus.NEEDS_REVIEW:
            result.needs_review += 1
        else:
            result.failed += 1
    return result


def understand_one(db: Session, job: JobPosting, *, call=call_llm, max_retries: int = 3) -> JobStatus:
    """Understand one job and save the result. Raises LLMError if the LLM fails."""
    text = job.description_text or ""
    if not text.strip():
        return _save(db, job, JobRequirements(title=job.title, extraction_status=ExtractionStatus.NEEDS_REVIEW),
                     flag_reason="Empty description")

    prompt, tampered = build_prompt(text)
    req = generate(prompt, JobRequirements, call=call, max_retries=max_retries)
    req = apply_source_fields(req, job.source_fields)          # A1: the source wins

    flag_reason = req.flag_reason
    if tampered or SUSPICIOUS.search(text):
        req = req.model_copy(update={"suspicious": True, "extraction_status": ExtractionStatus.NEEDS_REVIEW})
        flag_reason = INJECTION_REASON
    return _save(db, job, req, flag_reason)


def _save(db: Session, job: JobPosting, req: JobRequirements, flag_reason: str | None) -> JobStatus:
    """Write the job_requirement row (one per job) and set the job status."""
    row = job.requirement or JobRequirement(job_id=job.job_id)
    data = req.model_dump(exclude={"suspicious"})
    for name, value in data.items():
        setattr(row, name, value)
    row.flag_reason = flag_reason
    row.source_hash = job.content_hash          # which version of the posting was read
    row.parsed_at = datetime.now(timezone.utc)
    row.fit_score = None                        # requirements changed: P1-4 scores again
    row.fit_reason = None
    db.add(row)
    job.requirement = row

    ok = req.extraction_status == ExtractionStatus.OK and flag_reason is None
    job.status = JobStatus.PARSED if ok else JobStatus.NEEDS_REVIEW
    db.flush()
    return job.status