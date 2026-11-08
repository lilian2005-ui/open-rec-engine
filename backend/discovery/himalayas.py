"""Himalayas connector: turn one job from the Himalayas API into our JobPosting.

Field mapping follows data contract section 5. Structured fields (salary, employment
type, seniority, location and timezone restrictions) are kept as-is in source_fields,
whatever shape they come in.
"""
import logging
import os
from typing import Any


import httpx
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.config import settings as config
from backend.db.normalize import content_hash
from backend.discovery.cleaning import html_to_text
from backend.discovery.fetch import SourceFetchError, get_json
from backend.discovery.service import DiscoveryResult, load_settings, save_postings
from backend.schemas.enums import Source
from backend.schemas.job import JobPosting


logger = logging.getLogger(__name__)

# Without these a posting cannot be stored (JD-18).
REQUIRED_FIELDS = ("guid", "title", "companyName", "applicationLink", "description")
SOURCE_FIELDS = (
    "minSalary", "maxSalary", "currency", "salaryPeriod", "employmentType",
    "seniority", "locationRestrictions", "timezoneRestrictions",
)


class MappingError(ValueError):
    """A Himalayas job that cannot become a JobPosting. The caller skips it and logs why."""

def _source_fields(raw: dict) -> dict | None:
    """The SOURCE_FIELDS that have a value, unchanged; None when there are none."""
    fields = {k: raw[k] for k in SOURCE_FIELDS if raw.get(k) not in (None, "", [])}
    return fields or None

def map_job(raw: dict) -> JobPosting:
    """Map one Himalayas job (a dict from the API's "jobs" list) to a JobPosting.

    Raises MappingError when a required field is missing or a value is invalid.
    """
    missing = [field for field in REQUIRED_FIELDS if not raw.get(field)]
    if missing:
        raise MappingError(f"missing {', '.join(missing)}")

    description_text = html_to_text(raw["description"])
    if not description_text:
        raise MappingError("description is empty after removing HTML")

    try:
        return JobPosting(
            source=Source.HIMALAYAS,
            external_id=raw["guid"],
            url=raw["applicationLink"],  # Himalayas requires this link, not guid
            title=raw["title"],
            company_name=raw["companyName"],
            description_raw=raw["description"],
            description_text=description_text,
            content_hash=content_hash(raw["title"], description_text),
            posted_at=raw.get("pubDate") or None,      # Unix seconds -> UTC in the schema
            expires_at=raw.get("expiryDate") or None,
            source_fields=_source_fields(raw),
        )
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        raise MappingError(problems) from e


# ---------------------------------------------------------------- fetching

API_URL = "https://himalayas.app/jobs/api"
PAGE_SIZE = 20  # the API's maximum per request


def make_client(api_key: str | None = None, timeout: float = 30.0) -> httpx.Client:
    """An HTTP client for Himalayas. The key comes from HIMALAYAS_API_KEY (.env only).
    The API also works without a key, with a lower shared rate limit."""
    key = api_key if api_key is not None else (os.environ.get("HIMALAYAS_API_KEY") or config.HIMALAYAS_API_KEY)
    if not key:
        logger.warning("HIMALAYAS_API_KEY is not set; using the shared public rate limit")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return httpx.Client(headers=headers, timeout=timeout)



def _is_jobs_body(data: Any) -> bool:
    """True for an object holding a list of job objects, the only shape we can read."""
    jobs = data.get("jobs") if isinstance(data, dict) else None
    return isinstance(jobs, list) and all(isinstance(job, dict) for job in jobs)


def fetch_page(client: httpx.Client, cursor: str | None = None, max_retries: int = 3,
               page: int = 1) -> tuple[list[dict], str | None]:
    """One page: up to 20 jobs and the cursor of the next page (None on the last page).
    ``page`` is the 1-based page number. Raises SourceFetchError (see fetch.get_json)."""
    params: dict[str, str | int] = {"limit": PAGE_SIZE}
    if cursor:
        params["cursor"] = cursor
    data = get_json(client, API_URL, source="himalayas", page=page, max_retries=max_retries,
                    params=params, validate=_is_jobs_body)
    return data["jobs"], data.get("nextCursor")



def fetch_jobs(limit: int, client: httpx.Client,
               max_retries: int = 3) -> tuple[list[dict], SourceFetchError | None]:
    """The latest ``limit`` jobs, newest first, following nextCursor page by page.

    A job seen twice in one fetch (it can move to the next page while we read) is
    kept once (JD-07). A page that fails for good ends the fetch: the jobs read so far
    are returned with its error. The error is None when the fetch finished.
    """
    jobs: list[dict] = []
    seen: set[str] = set()
    cursor: str | None = None
    page_number = 1
    while len(jobs) < limit:
        try:
            page, next_cursor = fetch_page(client, cursor, max_retries, page_number)
        except SourceFetchError as e:
            logger.error("himalayas: fetch stopped at page %s with %d jobs: %s",
                         e.page, len(jobs), e)
            return jobs, e
        for job in page:
            guid = job.get("guid")
            if guid in seen:
                continue
            if guid:
                seen.add(guid)
            jobs.append(job)  # a job without guid is kept so map_job rejects and logs it
            if len(jobs) == limit:
                break
        if not page or not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        page_number += 1
    return jobs, None




# ---------------------------------------------------------------- the whole stage

def discover(db: Session, run_id: int, client: httpx.Client | None = None,
             raw_jobs: list[dict] | None = None) -> DiscoveryResult:
    """Fetch the latest fetch_limit Himalayas jobs and save them. Returns the counts.

    ``raw_jobs`` skips the API (e.g. the saved sample file). ``client`` lets tests pass
    a mocked HTTP client. All jobs are mapped before anything is saved. The caller commits.

    If a page fails, the jobs from earlier pages are still saved and result.error holds
    the failure. If the first page fails, nothing is saved. Nothing is raised either way.
    """
    error = None
    if raw_jobs is None:
        settings = load_settings(db)
        if client is None:
            with make_client() as own_client:
                raw_jobs, error = fetch_jobs(settings.fetch_limit, own_client, settings.max_retries)
        else:
            raw_jobs, error = fetch_jobs(settings.fetch_limit, client, settings.max_retries)

    result = DiscoveryResult(fetched=len(raw_jobs), error=error)
    postings: list[JobPosting] = []
    for raw in raw_jobs:
        try:
            postings.append(map_job(raw))
        except MappingError as e:
            result.skipped += 1
            logger.warning("himalayas: skipped job %s: %s", raw.get("guid") or "(no guid)", e)

    save_postings(db, postings, run_id, result)
    return result

