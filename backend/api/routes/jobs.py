"""Job routes (P2-4): the job feed, one job, and the person's correction (FR-12)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.api.deps import get_current_user
from backend.api.pagination import Page, PageParams, paginate
from backend.api.schemas import JobDetail, JobListItem, RequirementsEdit, RequirementsOut
from backend.db.models import Company, JobPosting, JobRequirement
from backend.db.session import get_db
from backend.schemas.enums import ExtractionStatus, JobStatus

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


@router.patch("/{job_id}/requirements", response_model=JobDetail)
def edit_requirements(job_id: int, body: RequirementsEdit, db: Session = Depends(get_db)):
    """A person corrects the extracted fields (FR-12). Only the sent fields change.

    The old fit was worked out from the old values, so it is cleared and the job goes
    back to ``parsed``: the next run scores it again with the corrected values.
    """
    job = db.get(JobPosting, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    requirement = _requirement(job)
    if requirement is None:
        raise HTTPException(404, "This job has no extracted requirements yet")

    changes = body.model_dump(exclude_unset=True)
    for field in ("required_skills", "preferred_skills"):
        if field in changes and changes[field] is None:
            changes[field] = []                  # the columns are lists, never null
    # salary_min <= salary_max, also when only one of the two is sent
    low = changes.get("salary_min", requirement.salary_min)
    high = changes.get("salary_max", requirement.salary_max)
    if low is not None and high is not None and low > high:
        raise HTTPException(422, "salary_min cannot be greater than salary_max")

    for field, value in changes.items():
        setattr(requirement, field, value)
    requirement.fit_score = None
    requirement.fit_reason = None
    requirement.flag_reason = None
    # a person has checked the values, so the job no longer waits for review
    requirement.extraction_status = ExtractionStatus.OK
    job.status = JobStatus.PARSED
    db.commit()
    return get_job(job_id, db)
