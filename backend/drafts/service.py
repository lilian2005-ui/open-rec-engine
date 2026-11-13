"""Stage 5 service (P2-1): one outreach draft for every qualified company.

Picks the leads whose status is ``qualified`` and that have no draft yet, asks the
LLM for a draft, checks it in code (``checks.py``), and saves it as version 1,
``pending_review``. The lead becomes ``draft_ready``. NOTHING IS EVER SENT (FR-25).

A new draft for a company that already has one is made only by Regenerate (P2-2).
"""
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from backend.db.models import Candidate, JobPosting, Lead, OutreachDraft
from backend.db.models.enums import DraftStatus, LeadStatus
from backend.drafts.checks import check_draft
from backend.drafts.prompt import build_draft_prompt, contact_of, first_name, with_retry_note
from backend.leads.reason import LLMCall
from backend.llm import LLMError, generate
from backend.llm import call_llm as shared_call_llm
from backend.schemas.draft import DraftOutput

log = logging.getLogger(__name__)

# A draft that breaks a rule in checks.py is asked for again, up to this many times.
CHECK_RETRIES = 2


@dataclass
class DraftRunResult:
    """What happened in one run of this stage (for the run log)."""

    created: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.errors)


class DraftRejected(Exception):
    """Every draft the LLM wrote broke at least one rule in checks.py."""


def leads_needing_a_draft(db: Session, limit: int | None = None) -> list[Lead]:
    """Qualified leads without any draft, best score first (so a small ``limit``
    tries the strongest companies)."""
    return list(db.scalars(
        select(Lead)
        .where(Lead.status == LeadStatus.QUALIFIED, ~Lead.drafts.any())
        .options(selectinload(Lead.company))
        .order_by(Lead.lead_score.desc(), Lead.lead_id)
        .limit(limit)
    ).all())


def roles_of(db: Session, lead: Lead) -> list[dict]:
    """The suitable jobs of the lead (``evidence.job_ids``), best fit first."""
    job_ids = lead.evidence.get("job_ids") or []
    jobs = db.scalars(
        select(JobPosting).where(JobPosting.job_id.in_(job_ids))
        .options(selectinload(JobPosting.requirement))
    ).all()
    roles = [{"title": j.title,
              "fit_score": j.requirement.fit_score if j.requirement else None,
              "fit_reason": j.requirement.fit_reason if j.requirement else None}
             for j in jobs]
    return sorted(roles, key=lambda r: -(r["fit_score"] or 0))


def write_draft(company_name: str, roles: list[dict], contact: dict | None,
                candidate_names: list[str], call: LLMCall = shared_call_llm) -> DraftOutput:
    """Ask for a draft and check it. Raises ``LLMError`` when the LLM gives no valid
    answer, and ``DraftRejected`` when every draft breaks a rule."""
    prompt = build_draft_prompt(company_name, roles, contact)
    problems: list[str] = []
    for attempt in range(1, CHECK_RETRIES + 2):
        asked = with_retry_note(prompt, problems) if problems else prompt
        draft = generate(asked, DraftOutput, call=call)    # retries a bad length by itself
        problems = check_draft(draft.subject, draft.body, company_name=company_name,
                               roles=roles, first_name=first_name(contact),
                               candidate_names=candidate_names)
        if not problems:
            return draft
        log.warning("draft for %s, attempt %d broke a rule: %s",
                    company_name, attempt, "; ".join(problems))
    raise DraftRejected("; ".join(problems))


def create_drafts(db: Session, call: LLMCall = shared_call_llm,
                  limit: int | None = None) -> DraftRunResult:
    """One draft for every qualified lead that has none (or only the first ``limit``).

    If no valid draft comes back, the lead stays ``qualified`` without a draft, the
    error is recorded and the other leads continue. The next run tries it again.
    """
    candidate_names = list(db.scalars(select(Candidate.display_name)).all())
    result = DraftRunResult()

    for lead in leads_needing_a_draft(db, limit):
        company = lead.company
        roles = roles_of(db, lead)
        contact = contact_of(company.contact_name, company.contact_title)

        try:
            draft = write_draft(company.name, roles, contact, candidate_names, call=call)
        except (LLMError, DraftRejected) as exc:
            msg = f"lead {lead.lead_id} ({company.name}): no draft: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue

        try:
            db.add(OutreachDraft(lead=lead, subject=draft.subject, body=draft.body,
                                 word_count=draft.word_count, version=1,
                                 status=DraftStatus.PENDING_REVIEW))
            lead.status = LeadStatus.DRAFT_READY
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            msg = f"lead {lead.lead_id} ({company.name}): could not save the draft: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue

        result.created += 1

    return result
