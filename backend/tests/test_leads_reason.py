"""P1-5: the lead reason (prompt, LLM answer, fallback). No database needed."""
import pytest

from backend.leads.reason import (NOT_QUALIFIED_REASON, build_reason_prompt, fallback_reason,
                                  write_reason)
from backend.llm import FakeLLM, LLMError

JOBS = [
    {"title": "Senior React Developer", "fit_score": 92, "fit_reason": "3 profiles cover React"},
    {"title": "Frontend Engineer", "fit_score": 78, "fit_reason": "2 profiles cover the stack"},
]


def test_prompt_holds_the_company_and_only_the_evidence_fields():
    jobs = [dict(JOBS[0], job_id=7, description_text="secret text")]
    prompt = build_reason_prompt("Acme Corp", jobs, 92)

    assert '"Acme Corp"' in prompt
    assert "Senior React Developer" in prompt and "92" in prompt
    assert "3 profiles cover React" in prompt
    assert "secret text" not in prompt and "job_id" not in prompt
    assert '{"reason": "..."}' in prompt          # literal braces survive str.format


def test_write_reason_returns_the_llm_sentence():
    fake = FakeLLM({"reason": "Acme has 2 suitable roles (92 and 78)."})

    assert write_reason("Acme Corp", JOBS, 97, call=fake) == "Acme has 2 suitable roles (92 and 78)."
    assert fake.calls == 1


def test_reason_longer_than_400_chars_is_rejected():
    fake = FakeLLM(*[{"reason": "x" * 401}] * 4)

    with pytest.raises(LLMError):
        write_reason("Acme Corp", JOBS, 97, call=fake)


def test_fallback_reason_is_built_from_the_numbers():
    assert fallback_reason(97, 92, 2) == (
        "2 suitable jobs; the best fit score is 92, which gives a lead score of 97.")
    assert fallback_reason(74, 74, 1).startswith("1 suitable job;")


def test_not_qualified_reason_is_not_empty():
    assert NOT_QUALIFIED_REASON.strip()
