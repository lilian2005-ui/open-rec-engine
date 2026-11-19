"""Shared LLM client: the only place in the project that talks to Gemini."""
import logging
import re
import threading
import time

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from backend.config import settings
from backend.schemas.common import gemini_schema

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The LLM could not give a valid answer. `attempts` = how many calls were made."""

    def __init__(self, message: str, attempts: int = 0):
        super().__init__(message)
        self.attempts = attempts


_pace_lock = threading.Lock()
_last_call = 0.0


def wait_for_slot(now=time.monotonic, sleep=time.sleep) -> None:
    """Keep at least LLM_MIN_INTERVAL_SECONDS between two Gemini calls.
    The free tier allows 15 requests per minute, so 4.5 s keeps us under it."""
    global _last_call
    with _pace_lock:
        gap = settings.LLM_MIN_INTERVAL_SECONDS - (now() - _last_call)
        if gap > 0:
            sleep(gap)
        _last_call = now()


def call_llm(prompt: str, response_schema: dict) -> str:
    """Send one prompt to Gemini and return the JSON text it answered with."""
    if not settings.GEMINI_API_KEY or not settings.LLM_MODEL:
        raise LLMError("GEMINI_API_KEY or LLM_MODEL is not set in .env")
    wait_for_slot()
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=settings.LLM_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=response_schema,
            temperature=0,
        ),
    )
    return response.text


def is_temporary(exc: Exception) -> bool:
    """Errors worth retrying: timeouts, connection problems, 429 and 5xx."""
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, errors.ServerError):
        return True
    return isinstance(exc, errors.ClientError) and exc.code == 429


def retry_wait(exc: Exception, attempt: int) -> float:
    """Seconds to wait before the next try.
    429 (quota): the time Gemini asks for ("retry in 48s"), or 60 s.
    5xx (busy):  10, 20, 30 s.  Timeouts and connection errors: 1, 2, 4 s."""
    if isinstance(exc, errors.ClientError) and exc.code == 429:
        found = re.search(r"retry in ([0-9.]+)s", str(exc))
        return min(float(found.group(1)) + 1, 65) if found else 60
    if isinstance(exc, errors.ServerError):
        return 10 * attempt
    return 2 ** (attempt - 1)


def generate(prompt: str, model: type[BaseModel], *, call=call_llm,
             max_retries: int = 3, sleep=time.sleep) -> BaseModel:
    """Ask the LLM and return a validated `model` object.
    Invalid answers and temporary errors are retried (max_retries=3 means up to 4 calls)."""
    schema = gemini_schema(model)
    problem = ""
    for attempt in range(1, max_retries + 2):
        try:
            return model.model_validate_json(call(prompt, schema))
        except ValidationError as exc:
            problem = f"invalid answer: {exc.errors()[0]['msg']}"
        except LLMError:
            raise
        except Exception as exc:
            if not is_temporary(exc):
                raise LLMError(f"LLM call failed: {exc}", attempt) from exc
            problem = f"temporary error: {exc}"
            if attempt <= max_retries:
                sleep(retry_wait(exc, attempt))
        log.warning("LLM attempt %d failed: %s", attempt, problem)
    raise LLMError(f"No valid answer after {attempt} attempts; last: {problem}", attempt)