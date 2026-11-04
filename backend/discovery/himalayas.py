"""Himalayas connector: turn one job from the Himalayas API into our JobPosting.

Field mapping follows data contract section 5. Fields we do not store
(timezoneRestrictions, locationRestrictions, seniority, salary, ...) are ignored,
whatever shape they come in.
"""
import logging
import os

import httpx
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.db.normalize import content_hash
from backend.discovery.cleaning import html_to_text
from backend.discovery.service import DiscoveryResult, load_settings, save_postings
from backend.schemas.enums import Source
from backend.schemas.job import JobPosting

logger = logging.getLogger(__name__)

# Without these a posting cannot be stored (JD-18).
REQUIRED_FIELDS = ("guid", "title", "companyName", "applicationLink", "description")


class MappingError(ValueError):
    """A Himalayas job that cannot become a JobPosting. The caller skips it and logs why."""


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
    key = api_key if api_key is not None else os.environ.get("HIMALAYAS_API_KEY")
    if not key:
        logger.warning("HIMALAYAS_API_KEY is not set; using the shared public rate limit")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return httpx.Client(headers=headers, timeout=timeout)



def fetch_page(client: httpx.Client, cursor: str | None = None) -> tuple[list[dict], str | None]:
    """One request: up to 20 jobs and the cursor of the next page (None on the last page)."""
    params: dict[str, str | int] = {"limit": PAGE_SIZE}
    if cursor:
        params["cursor"] = cursor
    response = client.get(API_URL, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("jobs") or [], data.get("nextCursor")



def fetch_jobs(limit: int, client: httpx.Client) -> list[dict]:
    """The latest ``limit`` jobs, newest first, following nextCursor page by page.

    A job seen twice in one fetch (it can move to the next page while we read) is
    kept once (JD-07). Retries and error handling belong to P1-2.
    """
    jobs: list[dict] = []
    seen: set[str] = set()
    cursor: str | None = None
    while len(jobs) < limit:
        page, next_cursor = fetch_page(client, cursor)
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
    return jobs




# ---------------------------------------------------------------- the whole stage

def discover(db: Session, run_id: int, client: httpx.Client | None = None,
             raw_jobs: list[dict] | None = None) -> DiscoveryResult:
    """Fetch the latest fetch_limit Himalayas jobs and save them. Returns the counts.

    ``raw_jobs`` skips the API (e.g. the saved sample file). ``client`` lets tests pass
    a mocked HTTP client. All jobs are mapped before anything is saved. The caller commits.
    """
    if raw_jobs is None:
        limit = load_settings(db).fetch_limit
        if client is None:
            with make_client() as own_client:
                raw_jobs = fetch_jobs(limit, own_client)
        else:
            raw_jobs = fetch_jobs(limit, client)

    result = DiscoveryResult(fetched=len(raw_jobs))
    postings: list[JobPosting] = []
    for raw in raw_jobs:
        try:
            postings.append(map_job(raw))
        except MappingError as e:
            result.skipped += 1
            logger.warning("himalayas: skipped job %s: %s", raw.get("guid") or "(no guid)", e)

    save_postings(db, postings, run_id, result)
    return result

