"""Stage 4 service (P1-5): the lead score of every company.

For each company that has jobs, picks its suitable jobs, computes the score in code
(``compute_lead_score``), gets a reason, and saves one ``lead`` row per company plus
one ``lead_snapshot`` row per company per run. Everything goes through the ORM.

A job is suitable when (data contract section 6, Q1, Q7):
- its status is ``scored``,
- its fit_score is at least ``lead_threshold`` (app_setting, default 60),
- ``expires_at`` is empty or still in the future.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from backend.db.models import Company, JobPosting, Lead, LeadSnapshot
from backend.db.models.enums import JobStatus, LeadStatus
from backend.discovery.service import load_settings
from backend.leads.reason import (NOT_QUALIFIED_REASON, LLMCall, fallback_reason,
                                  write_reason)
from backend.llm import LLMError
from backend.llm import call_llm as shared_call_llm
from backend.schemas.lead import LeadEvidence, LeadResult, compute_lead_score

log = logging.getLogger(__name__)

# Set by later stages (drafts and human review). A new score does not move them back,
# unless the company has no suitable job left (then it must be not_qualified).
KEPT_STATUSES = (LeadStatus.DRAFT_READY, LeadStatus.APPROVED, LeadStatus.REJECTED)


@dataclass
class LeadRunResult:
    """What happened in one run of this stage (for the run log)."""

    qualified: int = 0
    not_qualified: int = 0
    fallback_reasons: int = 0          # companies saved with the fallback sentence
    errors: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.errors)


def is_suitable(job: JobPosting, threshold: int, now: datetime) -> bool:
    req = job.requirement
    return (
        job.status == JobStatus.SCORED
        and req is not None
        and req.fit_score is not None
        and req.fit_score >= threshold
        and (job.expires_at is None or job.expires_at > now)
    )


def next_status(current: LeadStatus | None, qualifying_jobs: int) -> LeadStatus:
    """not_qualified if and only if there is no suitable job (database rule)."""
    if qualifying_jobs == 0:
        return LeadStatus.NOT_QUALIFIED
    if current in KEPT_STATUSES:
        return current
    return LeadStatus.QUALIFIED


def score_leads(db: Session, run_id: int, call: LLMCall = shared_call_llm,
                now: datetime | None = None) -> LeadRunResult:
    """Score every company that has jobs, for pipeline run ``run_id``.

    One company failing (database error) never stops the others (FR-29).
    """
    threshold = load_settings(db).lead_threshold
    now = now or datetime.now(timezone.utc)

    companies = db.scalars(
        select(Company)
        .where(Company.job_postings.any())
        .options(selectinload(Company.job_postings).selectinload(JobPosting.requirement),
                 selectinload(Company.lead))
        .order_by(Company.company_id)
    ).all()

    result = LeadRunResult()
    for company in companies:
        suitable = sorted(
            (j for j in company.job_postings if is_suitable(j, threshold, now)),
            key=lambda j: (-j.requirement.fit_score, j.job_id),
        )
        lead_score, best, n = compute_lead_score([j.requirement.fit_score for j in suitable])

        if n == 0:
            reason = NOT_QUALIFIED_REASON
        else:
            evidence_jobs = [{"title": j.title, "fit_score": j.requirement.fit_score,
                              "fit_reason": j.requirement.fit_reason} for j in suitable]
            try:
                reason = write_reason(company.name, evidence_jobs, lead_score, call=call)
            except LLMError as exc:
                log.warning("company %s: lead reason failed, using the fallback: %s",
                            company.company_id, exc)
                reason = fallback_reason(lead_score, best, n)
                result.fallback_reasons += 1

        lead = company.lead
        try:
            checked = LeadResult(
                company_id=company.company_id, run_id=run_id, lead_score=lead_score,
                best_job_score=best, qualifying_jobs=n,
                status=next_status(lead.status if lead else None, n), reason=reason,
                evidence=LeadEvidence(job_ids=sorted(j.job_id for j in suitable)),
            )
        except ValidationError as exc:
            msg = f"company {company.company_id}: invalid lead result: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue

        try:
            lead = save_lead(db, company, checked, now)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            msg = f"company {company.company_id}: could not save the lead: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue

        if checked.status == LeadStatus.NOT_QUALIFIED:
            result.not_qualified += 1
        else:
            result.qualified += 1

    return result


def save_lead(db: Session, company: Company, res: LeadResult, now: datetime) -> Lead:
    """Create or update the company's lead, and its snapshot for this run."""
    lead = company.lead
    if lead is None:
        # set through the relationship, so company.lead is filled in this session too
        lead = Lead(company=company)
        db.add(lead)
    lead.run_id = res.run_id
    lead.lead_score = res.lead_score
    lead.best_job_score = res.best_job_score
    lead.qualifying_jobs = res.qualifying_jobs
    lead.status = res.status
    lead.reason = res.reason
    lead.evidence = res.evidence.model_dump()
    lead.scored_at = now
    db.flush()  # gives a new lead its lead_id

    # One snapshot per company per run: running the same run again updates it.
    snap = db.scalar(select(LeadSnapshot).where(LeadSnapshot.lead_id == lead.lead_id,
                                                LeadSnapshot.run_id == res.run_id))
    if snap is None:
        snap = LeadSnapshot(lead_id=lead.lead_id, run_id=res.run_id)
        db.add(snap)
    snap.lead_score = res.lead_score
    snap.best_job_score = res.best_job_score
    snap.qualifying_jobs = res.qualifying_jobs
    snap.status = res.status
    return lead
