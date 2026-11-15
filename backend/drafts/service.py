"""Stage 5 service: outreach drafts for qualified companies.

P2-1 ``create_drafts``: picks the leads whose status is ``qualified``, asks the LLM
for a draft, checks it in code (``checks.py``), and saves it ``pending_review``.
The lead becomes ``draft_ready``. NOTHING IS EVER SENT (FR-25).

P2-2 ``regenerate_draft``: the reviewer asks for a new draft of one lead (FR-22).
The new draft is the next version; older versions are never changed (FR-24).

Both save through ``save_draft``, so the version is always worked out in one place.
"""
import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from backend.db.models import Candidate, JobPosting, Lead, OutreachDraft
from backend.db.models.enums import DraftStatus, LeadStatus
from backend.drafts.checks import check_draft
from backend.drafts.prompt import (build_draft_prompt, clean_note, contact_of, first_name,
                                   with_retry_note)
from backend.leads.reason import LLMCall
from backend.llm import LLMError, generate
from backend.llm import call_llm as shared_call_llm
from backend.schemas.draft import DraftOutput

log = logging.getLogger(__name__)

# A draft that breaks a rule in checks.py is asked for again, up to this many times.
CHECK_RETRIES = 2

# Regenerate is allowed for these lead statuses only (P2-2 card, "Rules").
CAN_REGENERATE = {LeadStatus.DRAFT_READY, LeadStatus.REJECTED, LeadStatus.QUALIFIED}
CANNOT_REGENERATE_MESSAGE = {
    LeadStatus.APPROVED: "This draft is already approved",
    LeadStatus.NOT_QUALIFIED: "This company has no suitable jobs",
}


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


class LeadNotFound(Exception):
    """No lead with this id (the API answers 404)."""


class CannotRegenerate(Exception):
    """The lead's status does not allow a new draft (the API answers 409)."""


# ---------- reading ----------

def leads_needing_a_draft(db: Session, limit: int | None = None) -> list[Lead]:
    """Qualified leads, best score first (so a small ``limit`` tries the strongest
    companies).

    A lead with older drafts is included too: after a draft a lead is ``draft_ready``,
    and lead scoring (P1-5) only makes it ``qualified`` again after it was
    ``not_qualified``. So "qualified with old drafts" means the company came back with
    new suitable jobs, and it gets the next version.
    """
    return list(db.scalars(
        select(Lead)
        .where(Lead.status == LeadStatus.QUALIFIED)
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


def candidate_names_of(db: Session) -> list[str]:
    """Every candidate display name (a draft must never name one)."""
    return list(db.scalars(select(Candidate.display_name)).all())


def latest_draft(db: Session, lead: Lead) -> OutreachDraft | None:
    return db.scalars(
        select(OutreachDraft).where(OutreachDraft.lead_id == lead.lead_id)
        .order_by(OutreachDraft.version.desc(), OutreachDraft.draft_id.desc())
        .limit(1)
    ).first()


def next_version(db: Session, lead: Lead) -> int:
    """The highest version of the lead's drafts + 1, or 1 when it has none."""
    top = db.scalar(select(func.max(OutreachDraft.version))
                    .where(OutreachDraft.lead_id == lead.lead_id))
    return (top or 0) + 1


# ---------- writing ----------

def write_draft(company_name: str, roles: list[dict], contact: dict | None,
                candidate_names: list[str], call: LLMCall = shared_call_llm,
                note: str | None = None) -> DraftOutput:
    """Ask for a draft and check it. ``note`` is the reviewer's note (P2-2).
    Raises ``LLMError`` when the LLM gives no valid answer, and ``DraftRejected``
    when every draft breaks a rule."""
    prompt = build_draft_prompt(company_name, roles, contact, note=note)
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


def save_draft(db: Session, lead: Lead, draft: DraftOutput) -> OutreachDraft:
    """Save the draft as the lead's next version, ``pending_review``, and make the
    lead ``draft_ready``. Older drafts are not touched. Commits.

    The lead row is locked while the version is worked out, so two saves at the
    same time (two Regenerate clicks) cannot get the same version.
    """
    db.execute(select(Lead.lead_id).where(Lead.lead_id == lead.lead_id).with_for_update())
    row = OutreachDraft(lead=lead, subject=draft.subject, body=draft.body,
                        word_count=draft.word_count, version=next_version(db, lead),
                        status=DraftStatus.PENDING_REVIEW)
    db.add(row)
    lead.status = LeadStatus.DRAFT_READY
    db.commit()
    return row


# ---------- P2-1: drafts for the pipeline run ----------

def create_drafts(db: Session, call: LLMCall = shared_call_llm,
                  limit: int | None = None) -> DraftRunResult:
    """A draft for every qualified lead (or only the first ``limit``).

    If no valid draft comes back, the lead stays ``qualified``, the error is recorded
    and the other leads continue. The next run tries it again.
    """
    candidate_names = candidate_names_of(db)
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
            save_draft(db, lead, draft)
        except SQLAlchemyError as exc:
            db.rollback()
            msg = f"lead {lead.lead_id} ({company.name}): could not save the draft: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue

        result.created += 1

    return result


# ---------- P2-2: Regenerate ----------

def regenerate_draft(db: Session, lead_id: int, *, note: str | None = None,
                     call: LLMCall = shared_call_llm) -> OutreachDraft:
    """A new draft for one lead, as the next version (FR-22).

    ``note`` is what the reviewer wants fixed. Without one, the review comment of the
    latest draft is used when that draft was rejected.

    Raises ``LeadNotFound`` (404), ``CannotRegenerate`` (409), and ``LLMError`` or
    ``DraftRejected`` when no valid draft comes back (502). On any error nothing
    changes: the older drafts and the lead's status stay as they were.
    """
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise LeadNotFound(f"Lead {lead_id} not found")
    if lead.status not in CAN_REGENERATE:
        raise CannotRegenerate(CANNOT_REGENERATE_MESSAGE.get(
            lead.status, f"Cannot regenerate a draft for a {lead.status.value} lead"))

    note = clean_note(note)
    if note is None:
        last = latest_draft(db, lead)
        if last is not None and last.status == DraftStatus.REJECTED:
            note = clean_note(last.review_comment)

    company = lead.company
    draft = write_draft(company.name, roles_of(db, lead),
                        contact_of(company.contact_name, company.contact_title),
                        candidate_names_of(db), call=call, note=note)

    # The LLM takes seconds; a reviewer may have approved in the meantime. Lock the
    # lead (as save_draft and the review routes do) and check its status again.
    db.execute(select(Lead.lead_id).where(Lead.lead_id == lead.lead_id).with_for_update())
    db.refresh(lead)
    if lead.status not in CAN_REGENERATE:
        raise CannotRegenerate(CANNOT_REGENERATE_MESSAGE.get(
            lead.status, f"Cannot regenerate a draft for a {lead.status.value} lead"))
    try:
        return save_draft(db, lead, draft)
    except SQLAlchemyError:
        db.rollback()
        raise
