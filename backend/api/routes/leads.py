"""Lead routes (P2-5): ranked companies, the review page, and the contact."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.api.deps import get_current_user
from backend.api.pagination import Page, PageParams, paginate
from backend.api.schemas import (CompanyOut, ContactUpdate, DraftOut, LeadDetail,
                                 LeadHistoryOut, LeadJobOut, LeadListItem)
from backend.db.models import Company, JobPosting, Lead
from backend.db.session import get_db
from backend.drafts.service import (CannotRegenerate, DraftRejected, LeadNotFound,
                                    latest_draft, regenerate_draft)
from backend.leads.reason import LLMCall
from backend.llm import LLMError, call_llm
from backend.schemas.enums import LeadStatus

router = APIRouter(prefix="/leads", tags=["leads"], dependencies=[Depends(get_current_user)])


def _list_fields(lead: Lead) -> dict:
    return {
        "lead_id": lead.lead_id,
        "company_name": lead.company.name,
        "lead_score": lead.lead_score,
        "best_job_score": lead.best_job_score,
        "qualifying_jobs": lead.qualifying_jobs,
        "status": lead.status,
        "reason": lead.reason,
    }


def _get_lead(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "Lead not found")
    return lead


@router.get("", response_model=Page[LeadListItem])
def list_leads(status: LeadStatus | None = None, params: PageParams = Depends(),
               db: Session = Depends(get_db)):
    """Companies: not_qualified always last; in each group the highest lead score
    first, then by name."""
    stmt = (
        select(Lead).join(Lead.company)
        .options(selectinload(Lead.company))    # with the page, not one query per lead
        .order_by((Lead.status == LeadStatus.NOT_QUALIFIED).asc(),   # false (0) first
                  Lead.lead_score.desc(), Company.name, Lead.lead_id)
    )
    if status:
        stmt = stmt.where(Lead.status == status)
    leads, total = paginate(db, stmt, params)
    return Page(items=[LeadListItem(**_list_fields(x)) for x in leads], total=total,
                page=params.page, page_size=params.page_size)


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    """The review page of one company: its jobs, score history and newest draft."""
    lead = _get_lead(db, lead_id)

    # only the jobs that counted in the score (evidence), best fit first
    jobs = db.scalars(
        select(JobPosting).where(JobPosting.job_id.in_(lead.evidence.get("job_ids") or []))
        .options(selectinload(JobPosting.requirement))
    ).all()
    job_rows = [LeadJobOut(job_id=j.job_id, title=j.title,
                           fit_score=j.requirement.fit_score if j.requirement else None,
                           fit_reason=j.requirement.fit_reason if j.requirement else None)
                for j in jobs]
    job_rows.sort(key=lambda j: (-(j.fit_score or 0), j.job_id))

    latest = latest_draft(db, lead)
    return LeadDetail(
        **_list_fields(lead),
        company=CompanyOut.model_validate(lead.company),
        jobs=job_rows,
        history=[LeadHistoryOut.model_validate(s)
                 for s in sorted(lead.snapshots, key=lambda s: s.created_at)],
        draft=DraftOut.model_validate(latest) if latest else None,
    )


@router.patch("/{lead_id}/contact", response_model=CompanyOut)
def update_contact(lead_id: int, body: ContactUpdate, db: Session = Depends(get_db)):
    """A person types the contact in. No AI here."""
    company = _get_lead(db, lead_id).company
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    return company


def get_llm_call() -> LLMCall:
    """The LLM that Regenerate uses. Tests replace it with FakeLLM through
    app.dependency_overrides, so they never call Gemini."""
    return call_llm


@router.post("/{lead_id}/draft/regenerate", response_model=DraftOut, status_code=201)
def regenerate(lead_id: int, db: Session = Depends(get_db),
               call: LLMCall = Depends(get_llm_call)):
    """A new draft as the next version (P2-2). No body: when the latest draft was
    rejected, the service uses its review comment as the note."""
    try:
        return regenerate_draft(db, lead_id, call=call)
    except LeadNotFound:
        raise HTTPException(404, "Lead not found")
    except CannotRegenerate as exc:
        raise HTTPException(409, str(exc))
    except (LLMError, DraftRejected):
        # the details are in the server log; nothing was saved
        raise HTTPException(502, "Could not write a valid draft. Please try again.")
