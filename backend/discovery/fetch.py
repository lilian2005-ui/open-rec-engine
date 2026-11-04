"""Fetching JSON from a job source, retrying temporary failures. Works for every source.

The caller passes max_retries (from app_setting) and an httpx.Client that already holds
any API key in its headers. Never put a key in the URL or params: httpx logs full URLs.
"""
import logging
import time
from collections.abc import Callable, Mapping
from itertools import count
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRY_AFTER = 60  # seconds; a server cannot make us wait longer than this
TEMPORARY_ERRORS = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


class SourceFetchError(Exception):
    """A source request that failed for good: retries used up, or a permanent error.

    ``error_type`` is "http_status", "invalid_body" or an httpx exception name. The
    message never holds the URL, headers or response body, so it is safe to store.
    """

    def __init__(self, source: str, page: int | str | None, error_type: str,
                 status: int | None, attempts: int, message: str) -> None:
        super().__init__(message)
        self.source = source
        self.page = page
        self.error_type = error_type
        self.status = status
        self.attempts = attempts
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe dict for pipeline_run.errors (grouped by stage and source)."""
        return {
            "stage": "discovery",
            "source": self.source,
            "page": self.page,
            "error_type": self.error_type,
            "status": self.status,
            "attempts": self.attempts,
            "message": self.message,
        }


def _retry_after(response: httpx.Response) -> int | None:
    """The Retry-After wait in seconds, capped. None when it is not a whole number."""
    value = response.headers.get("Retry-After", "").strip()
    return min(int(value), MAX_RETRY_AFTER) if value.isdecimal() else None


def get_json(client: httpx.Client, url: str, *, source: str, page: int | str | None,
             max_retries: int, params: Mapping[str, str | int] | None = None,
             timeout: float = 10.0, sleep: Callable[[float], None] = time.sleep) -> Any:
    """GET ``url`` and return its JSON body, making at most max_retries + 1 requests.

    Timeouts, connection errors, 429 and 5xx are retried after 1, 2, then 4 s (on 429,
    after Retry-After if present). ``page`` is the page or cursor, used to report failures.
    Raises SourceFetchError when retries run out or on a permanent error.
    """
    for attempt in count(1):
        retry_after = None
        try:
            response = client.get(url, params=params, timeout=timeout)
        except TEMPORARY_ERRORS as e:
            error_type = reason = type(e).__name__
            status = None
        except httpx.HTTPError as e:
            error_type = type(e).__name__
            raise SourceFetchError(source, page, error_type, None, attempt,
                                   f"{error_type} (not retried)") from e
        else:
            status = response.status_code
            if response.is_success:
                try:
                    return response.json()
                except ValueError as e:
                    raise SourceFetchError(source, page, "invalid_body", status, attempt,
                                           "response body is not valid JSON") from e
            error_type = "http_status"
            reason = f"HTTP {status}"
            if status != 429 and status < 500:
                raise SourceFetchError(source, page, error_type, status, attempt,
                                       f"{reason} (not retried)")
            if status == 429:
                retry_after = _retry_after(response)

        if attempt > max_retries:
            raise SourceFetchError(source, page, error_type, status, attempt,
                                   f"{reason} after {attempt} attempts")
        wait = 2 ** (attempt - 1) if retry_after is None else retry_after
        logger.warning("%s: page %s attempt %d failed (%s), retrying in %d s",
                       source, page, attempt, reason, wait)
        sleep(wait)
