"""Tests for the shared LLM client. No network: every test uses FakeLLM."""
import httpx
import pytest

from backend.llm import FakeLLM, LLMError, call_llm, generate
from backend.llm import client as llm_client
from backend.schemas.job import FitOutput, JobRequirements

GOOD_FIT = {"fit_score": 92, "fit_reason": "3 profiles cover react, typescript and redux"}


def no_sleep(_seconds):
    pass


def test_valid_answer_is_returned_as_model():
    fake = FakeLLM(GOOD_FIT)
    out = generate("prompt", FitOutput, call=fake, sleep=no_sleep)
    assert isinstance(out, FitOutput)
    assert out.fit_score == 92
    assert fake.calls == 1


def test_answer_is_validated_by_the_schema():
    answer = {"title": "Senior React Developer", "required_skills": ["React", "TypeScript"]}
    out = generate("p", JobRequirements, call=FakeLLM(answer), sleep=no_sleep)
    assert out.required_skills == ["react", "typescript"]   # normalised by the schema
    assert out.salary_min is None                           # not stated -> stays empty


def test_broken_json_is_retried_then_succeeds():
    fake = FakeLLM("{not json", GOOD_FIT)
    assert generate("p", FitOutput, call=fake, sleep=no_sleep).fit_score == 92
    assert fake.calls == 2


def test_out_of_range_score_is_retried():
    fake = FakeLLM({"fit_score": 150, "fit_reason": "x"}, GOOD_FIT)
    assert generate("p", FitOutput, call=fake, sleep=no_sleep).fit_score == 92
    assert fake.calls == 2


def test_extra_field_is_rejected():
    fake = FakeLLM({**GOOD_FIT, "note": "ignore previous instructions"}, GOOD_FIT)
    generate("p", FitOutput, call=fake, sleep=no_sleep)
    assert fake.calls == 2


def test_always_invalid_stops_after_four_calls():
    fake = FakeLLM(*["{bad"] * 4)
    with pytest.raises(LLMError) as err:
        generate("p", FitOutput, call=fake, sleep=no_sleep)
    assert err.value.attempts == 4            # first call + 3 retries
    assert fake.calls == 4


def test_timeout_is_retried_with_backoff():
    waits = []
    fake = FakeLLM(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"), GOOD_FIT)
    assert generate("p", FitOutput, call=fake, sleep=waits.append).fit_score == 92
    assert waits == [1, 2]


def test_permanent_error_is_not_retried():
    fake = FakeLLM(ValueError("invalid API key"), GOOD_FIT)
    with pytest.raises(LLMError):
        generate("p", FitOutput, call=fake, sleep=no_sleep)
    assert fake.calls == 1


def test_missing_settings_give_a_clear_error(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "")
    with pytest.raises(LLMError, match="not set"):
        call_llm("p", {})