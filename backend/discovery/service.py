"""Saving discovered jobs to the database. Works for every source: a connector
(himalayas.py, later remotive.py) gives JobPosting objects, this module stores them."""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import AppSetting, Company
from backend.db.models import JobPosting as JobPostingRow
from backend.db.normalize import company_name_key
from backend.discovery.fetch import SourceFetchError
from backend.schemas.enums import JobStatus
from backend.schemas.job import JobPosting
from backend.schemas.settings import AppSettings



@dataclass
class DiscoveryResult:
    """Counts for the run log (pipeline_run.jobs_fetched / jobs_new / jobs_updated) and
    the failure that ended the fetch, if any (error.to_dict() goes in pipeline_run.errors)."""
    fetched: int = 0    # jobs returned by the source
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0    # could not be mapped (missing or invalid fields)
    error: SourceFetchError | None = None  # the counts cover the pages before this failure

def load_settings(db: Session) -> AppSettings:
    """The editable settings from app_setting (fetch_limit, ...), parsed and validated.
    A missing key gets its default."""
    rows = db.execute(select(AppSetting.key, AppSetting.value)).all()
    return AppSettings.from_rows(dict(rows))



def get_or_create_company(db: Session, name: str) -> Company:
    """The company with this normalized name (Q2), created if it does not exist yet.
    flush() makes a new company visible to the next lookup in the same run (JD-13)."""
    key = company_name_key(name)
    company = db.scalar(select(Company).where(Company.normalized_name == key))
    if company is None:
        company = Company(name=name, normalized_name=key)
        db.add(company)
        db.flush()
    return company



def upsert_job(db: Session, posting: JobPosting, company_id: int, run_id: int) -> str:
    """Save one posting and return "new", "updated" or "unchanged".

    Found by (source, external_id). A new posting is added as discovered. A changed
    one (new content_hash) updates the same row and goes back to discovered (Q1).
    An unchanged one is left as it is. Nothing is ever deleted (JD-38).
    """
    row = db.scalar(
        select(JobPostingRow).where(
            JobPostingRow.source == posting.source,
            JobPostingRow.external_id == posting.external_id,
        )
    )
    if row is None:
        db.add(JobPostingRow(
            company_id=company_id,
            run_id=run_id,
            source=posting.source,
            external_id=posting.external_id,
            url=posting.url,
            title=posting.title,
            description_raw=posting.description_raw,
            description_text=posting.description_text,
            content_hash=posting.content_hash,
            posted_at=posting.posted_at,
            expires_at=posting.expires_at,
            status=JobStatus.DISCOVERED,
        ))
        db.flush()
        return "new"

    if row.content_hash == posting.content_hash:
        return "unchanged"

    row.company_id = company_id
    row.run_id = run_id
    row.url = posting.url
    row.title = posting.title
    row.description_raw = posting.description_raw
    row.description_text = posting.description_text
    row.content_hash = posting.content_hash
    row.posted_at = posting.posted_at
    row.expires_at = posting.expires_at
    row.updated_at = datetime.now(timezone.utc)
    row.status = JobStatus.DISCOVERED
    db.flush()
    return "updated"



def save_postings(db: Session, postings: list[JobPosting], run_id: int, result: DiscoveryResult) -> None:
    """Save every posting with its company and add the outcomes to ``result``."""
    for posting in postings:
        company = get_or_create_company(db, posting.company_name)
        outcome = upsert_job(db, posting, company.company_id, run_id)
        setattr(result, outcome, getattr(result, outcome) + 1)
