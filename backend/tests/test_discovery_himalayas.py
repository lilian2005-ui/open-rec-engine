"""P1-2: Himalayas pages through get_json, and what a failed page does to a run.
Fake pages are built from the real sample response. No network and no real waiting."""
import json
import logging
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from backend.db.models import AppSetting, PipelineRun
from backend.db.models import JobPosting as JobPostingRow
from backend.db.models.enums import RunStatus, TriggerType
from backend.discovery import himalayas
from backend.discovery.fetch import SourceFetchError, get_json
from backend.discovery.himalayas import discover, fetch_jobs, fetch_page, make_client
from backend.schemas.settings import AppSettings

SAMPLE_FILE = Path(__file__).resolve().parents[2] / "data" / "samples" / "himalayas.json"
SAMPLE = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
JOBS_PER_PAGE = len(SAMPLE["jobs"])
API_KEY = "secret-key-123"
RUN_ID = 1


def error(code: int) -> httpx.Response:
    return httpx.Response(code)


def bad_body(body) -> httpx.Response:
    return httpx.Response(200, json=body)


class FakeHimalayas:
    """Serves ``total`` pages of the sample, found by cursor. ``script`` maps a page number
    to steps played one per request, the last one repeating. A step is a response to
    return, an exception to raise, or None to serve the real page."""

    def __init__(self, total: int = 5, script: dict[int, list] | None = None):
        self.total = total
        self.script = script or {}
        self.pages: list[int] = []  # the page number of each request

    def __call__(self, request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        number = int(cursor.removeprefix("cursor-")) if cursor else 1
        self.pages.append(number)
        steps = self.script.get(number, [None])
        step = steps[min(self.pages.count(number), len(steps)) - 1]
        if isinstance(step, Exception):
            raise step
        return step or httpx.Response(200, json=self.page(number))

    def page(self, number: int) -> dict:
        jobs = [{**job, "guid": f"p{number}-{job['guid']}"} for job in SAMPLE["jobs"]]
        next_cursor = f"cursor-{number + 1}" if number < self.total else None
        return {**SAMPLE, "jobs": jobs, "nextCursor": next_cursor}

    def client(self, api_key: str | None = None) -> httpx.Client:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        return httpx.Client(transport=httpx.MockTransport(self), headers=headers)


@pytest.fixture(autouse=True)
def waits(monkeypatch) -> list[float]:
    """The waits get_json asked for. sleep is bound as a default, so time.sleep can't be patched."""
    waits: list[float] = []
    monkeypatch.setattr(himalayas, "get_json", partial(get_json, sleep=waits.append))
    return waits


@pytest.fixture
def saved(monkeypatch) -> list:
    """Runs discover() without a database: default settings, postings collected here."""
    postings: list = []

    def save_postings(db, new_postings, run_id, result):
        postings.extend(new_postings)
        result.new += len(new_postings)

    monkeypatch.setattr(himalayas, "save_postings", save_postings)
    monkeypatch.setattr(himalayas, "load_settings", lambda db: AppSettings())
    return postings


def assert_counts_add_up(result) -> None:
    assert result.fetched == result.new + result.updated + result.unchanged + result.skipped


# ---------------------------------------------------------------- partial failure

def test_page_3_of_5_failing_keeps_pages_1_and_2(saved):
    server = FakeHimalayas(script={3: [error(401)]})
    result = discover(None, RUN_ID, client=server.client())

    assert server.pages == [1, 2, 3]
    assert result.fetched == result.new == 2 * JOBS_PER_PAGE
    assert_counts_add_up(result)
    expected = [f"p{n}-{job['guid']}" for n in (1, 2) for job in SAMPLE["jobs"]]
    assert [posting.external_id for posting in saved] == expected
    assert result.error.page == 3
    assert result.error.to_dict() == {
        "stage": "discovery", "source": "himalayas", "page": 3, "error_type": "http_status",
        "status": 401, "attempts": 1, "message": "HTTP 401 (not retried)",
    }


def test_page_failing_after_all_retries_keeps_earlier_pages(saved):
    server = FakeHimalayas(script={3: [error(503)]})
    result = discover(None, RUN_ID, client=server.client())

    assert server.pages == [1, 2, 3, 3, 3, 3]
    assert len(saved) == 2 * JOBS_PER_PAGE
    assert (result.error.page, result.error.attempts) == (3, 4)


def test_first_page_failing_saves_nothing_and_returns_the_error(saved):
    server = FakeHimalayas(script={1: [error(401)]})
    result = discover(None, RUN_ID, client=server.client())

    assert saved == []
    assert result.fetched == 0
    assert_counts_add_up(result)
    assert (result.error.page, result.error.status) == (1, 401)


def test_temporary_failure_on_page_2_recovers(saved, waits):
    server = FakeHimalayas(script={2: [error(503), httpx.ReadTimeout("slow"), None]})
    result = discover(None, RUN_ID, client=server.client())

    assert server.pages == [1, 2, 2, 2, 3, 4, 5]
    assert waits == [1, 2]
    assert result.error is None
    assert result.fetched == result.new == 5 * JOBS_PER_PAGE
    assert len(saved) == 5 * JOBS_PER_PAGE


def test_a_failed_page_after_the_limit_is_never_requested():
    server = FakeHimalayas(script={3: [error(401)]})
    with server.client() as client:
        jobs, failure = fetch_jobs(2 * JOBS_PER_PAGE, client)
    assert len(jobs) == 2 * JOBS_PER_PAGE
    assert failure is None
    assert server.pages == [1, 2]


def test_the_failure_is_logged_once(caplog):
    server = FakeHimalayas(script={2: [error(401)]})
    with caplog.at_level(logging.ERROR, logger="backend.discovery.himalayas"), server.client() as client:
        fetch_jobs(100, client)
    assert [r.getMessage() for r in caplog.records] == [
        f"himalayas: fetch stopped at page 2 with {JOBS_PER_PAGE} jobs: HTTP 401 (not retried)",
    ]


def test_discover_with_its_own_client_also_returns_the_error(saved, monkeypatch):
    server = FakeHimalayas(script={2: [error(401)]})
    monkeypatch.setattr(himalayas, "make_client", server.client)
    result = discover(None, RUN_ID)
    assert len(saved) == JOBS_PER_PAGE
    assert result.error.page == 2


def test_raw_jobs_use_no_settings_and_have_no_error(saved, monkeypatch):
    monkeypatch.setattr(himalayas, "load_settings", None)
    result = discover(None, RUN_ID, raw_jobs=SAMPLE["jobs"])
    assert result.fetched == JOBS_PER_PAGE
    assert result.error is None


# ---------------------------------------------------------------- response shape

BAD_BODIES = [[], "jobs", 7, None, {}, {"jobs": None}, {"jobs": "x"}, {"jobs": {}}, {"jobs": [1]},
              {"jobs": [{"guid": "a"}, None]}]


@pytest.mark.parametrize("body", BAD_BODIES)
def test_body_without_a_jobs_list_is_invalid(body):
    server = FakeHimalayas(script={1: [bad_body(body)]})
    with server.client() as client, pytest.raises(SourceFetchError) as e:
        fetch_page(client)
    assert (e.value.error_type, e.value.status, e.value.page) == ("invalid_body", 200, 1)
    assert e.value.attempts == 1
    assert server.pages == [1]


def test_invalid_body_reports_the_real_attempt_count():
    server = FakeHimalayas(script={1: [error(503), error(503), bad_body({})]})
    with server.client() as client, pytest.raises(SourceFetchError) as e:
        fetch_page(client)
    assert e.value.attempts == 3


@pytest.mark.parametrize("body", BAD_BODIES)
def test_discover_returns_an_invalid_body_instead_of_crashing(saved, body):
    server = FakeHimalayas(script={2: [bad_body(body)]})
    result = discover(None, RUN_ID, client=server.client())
    assert len(saved) == JOBS_PER_PAGE
    assert (result.error.error_type, result.error.page) == ("invalid_body", 2)


def test_an_empty_jobs_list_is_a_normal_last_page():
    server = FakeHimalayas(script={2: [bad_body({"jobs": []})]})
    with server.client() as client:
        jobs, failure = fetch_jobs(100, client)
    assert len(jobs) == JOBS_PER_PAGE
    assert failure is None


# ---------------------------------------------------------------- max_retries

@pytest.mark.parametrize("max_retries, requests", [(0, 1), (1, 2), (5, 6)])
def test_max_retries_comes_from_the_settings(saved, monkeypatch, max_retries, requests):
    monkeypatch.setattr(himalayas, "load_settings",
                        lambda db: AppSettings(max_retries=max_retries))
    server = FakeHimalayas(script={1: [error(503)]})
    result = discover(None, RUN_ID, client=server.client())
    assert len(server.pages) == requests
    assert result.error.attempts == requests


def test_max_retries_also_applies_to_discovers_own_client(saved, monkeypatch):
    monkeypatch.setattr(himalayas, "load_settings", lambda db: AppSettings(max_retries=1))
    server = FakeHimalayas(script={1: [error(503)]})
    monkeypatch.setattr(himalayas, "make_client", server.client)
    assert discover(None, RUN_ID).error.attempts == 2
    assert len(server.pages) == 2


def test_fetch_limit_also_applies_to_discovers_own_client(saved, monkeypatch):
    monkeypatch.setattr(himalayas, "load_settings", lambda db: AppSettings(fetch_limit=25))
    server = FakeHimalayas()
    monkeypatch.setattr(himalayas, "make_client", server.client)
    assert discover(None, RUN_ID).fetched == 25


def test_fetch_limit_still_comes_from_the_settings(saved, monkeypatch):
    monkeypatch.setattr(himalayas, "load_settings", lambda db: AppSettings(fetch_limit=25))
    server = FakeHimalayas()
    assert discover(None, RUN_ID, client=server.client()).fetched == 25
    assert server.pages == [1, 2]


# ---------------------------------------------------------------- the API key

@pytest.mark.parametrize("step", [error(401), error(503), httpx.ReadTimeout("slow"),
                                  httpx.UnsupportedProtocol("bad scheme"), bad_body({}),
                                  httpx.Response(200, content=b"not json")])
def test_api_key_never_appears_through_discover(saved, caplog, step):
    server = FakeHimalayas(script={2: [step]})
    with caplog.at_level(logging.DEBUG):
        result = discover(None, RUN_ID, client=server.client(API_KEY))
    assert result.error is not None
    assert API_KEY not in str(result.error)
    assert API_KEY not in repr(result)
    assert API_KEY not in json.dumps(result.error.to_dict())
    assert API_KEY not in caplog.text


def test_make_client_keeps_the_key_in_the_header():
    with make_client(API_KEY) as client:
        assert client.headers["Authorization"] == f"Bearer {API_KEY}"
        assert API_KEY not in str(client.params)


def test_page_requests_use_the_30_second_timeout_of_make_client(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json=SAMPLE)

    real_client = httpx.Client

    def client_with_mock_transport(*args, **kwargs):
        # transport= at construction also turns off env and system proxies
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(himalayas.httpx, "Client", client_with_mock_transport)
    with make_client(API_KEY) as client:
        fetch_page(client)
    assert seen == [{"connect": 30.0, "read": 30.0, "write": 30.0, "pool": 30.0}]


# ---------------------------------------------------------------- with the database

@pytest.fixture
def run_id(db) -> int:
    run = PipelineRun(trigger_type=TriggerType.MANUAL, status=RunStatus.RUNNING,
                      started_at=datetime.now(timezone.utc))
    db.add(run)
    db.flush()
    return run.run_id


def stored(db, run_id: int) -> int:
    return db.scalar(select(func.count()).select_from(JobPostingRow)
                     .where(JobPostingRow.run_id == run_id))


def test_db_page_3_failing_stores_pages_1_and_2(db, run_id):
    server = FakeHimalayas(script={3: [error(401)]})
    result = discover(db, run_id, client=server.client())
    assert stored(db, run_id) == result.new == 2 * JOBS_PER_PAGE
    assert_counts_add_up(result)
    assert result.error.page == 3


def test_db_first_page_failing_stores_nothing(db, run_id):
    server = FakeHimalayas(script={1: [error(401)]})
    result = discover(db, run_id, client=server.client())
    assert stored(db, run_id) == 0
    assert result.error.page == 1


def test_db_max_retries_is_read_from_app_setting(db, run_id):
    db.merge(AppSetting(key="max_retries", value="1"))
    db.flush()
    server = FakeHimalayas(script={1: [error(503)]})
    result = discover(db, run_id, client=server.client())
    assert len(server.pages) == 2
    assert result.error.attempts == 2
