"""Job routes (P2-4): the job feed and one job."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.api.deps import get_current_user
from backend.api.pagination import Page, PageParams, paginate
from backend.api.schemas import JobDetail, JobListItem, RequirementsOut
from backend.db.models import Company, JobPosting, JobRequirement
from backend.db.session import get_db
from backend.schemas.enums import JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])


def _requirement(job: JobPosting) -> JobRequirement | None:
    """The job's requirements, or None while it is discovered. A posting that changed
    at the source goes back to discovered but keeps its old row until it is parsed
    again (Q1); that old row describes the old text, so it is not shown."""
    return None if job.status == JobStatus.DISCOVERED else job.requirement


def _list_fields(job: JobPosting) -> dict:
    requirement = _requirement(job)
    return {
        "job_id": job.job_id,
        "title": job.title,
        "company_name": job.company.name,
        "source": job.source,
        "posted_at": job.posted_at,
        "status": job.status,
        "fit_score": requirement.fit_score if requirement else None,
    }


@router.get("", response_model=Page[JobListItem])
def list_jobs(status: JobStatus | None = None, q: str | None = None,
              params: PageParams = Depends(), db: Session = Depends(get_db)):
    """Jobs, newest first (no posted_at goes last). ``q`` searches the title or the
    company name."""
    stmt = (
        select(JobPosting).join(JobPosting.company)
        # company and requirement come with the page, not one query per job
        .options(selectinload(JobPosting.company), selectinload(JobPosting.requirement))
        .order_by(JobPosting.posted_at.desc().nulls_last(), JobPosting.job_id.desc())
    )
    if status:
        stmt = stmt.where(JobPosting.status == status)
    if q:
        stmt = stmt.where(or_(JobPosting.title.icontains(q, autoescape=True),
                              Company.name.icontains(q, autoescape=True)))
    jobs, total = paginate(db, stmt, params)
    return Page(items=[JobListItem(**_list_fields(j)) for j in jobs], total=total,
                page=params.page, page_size=params.page_size)


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(JobPosting, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    requirement = _requirement(job)
    return JobDetail(
        **_list_fields(job),
        url=job.url,
        description_text=job.description_text,
        expires_at=job.expires_at,
        requirements=RequirementsOut.model_validate(requirement) if requirement else None,
    )
