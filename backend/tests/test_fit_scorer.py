import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.fit.scorer import FakeFitScorer, GeminiFitScorer, build_prompt

REQ = {"title": "Senior React Developer", "seniority": "senior", "min_years_experience": 5,
       "required_skills": ["react", "typescript"], "preferred_skills": ["graphql"],
       "timezone_offsets": [-5], "salary_min": 90000}
POOL = [
    {"candidate_id": 101, "display_name": "Candidate 101", "headline": "Senior Frontend",
     "years_experience": Decimal("7.5"), "seniority": "senior", "skills": ["react", "redux"],
     "timezone_offsets": [-5], "availability": "now", "summary": "secret summary"},
    {"candidate_id": 102, "display_name": "Candidate 102", "headline": "Backend",
     "years_experience": Decimal("3.0"), "seniority": "mid", "skills": ["python"],
     "timezone_offsets": None, "availability": "now", "summary": "x"},
]


def good_llm(prompt, schema):
    return json.dumps({"fit_score": 92, "fit_reason": "Our pool has 1 profile with react."})


def test_prompt_has_only_the_needed_fields():
    p = build_prompt(REQ, POOL)
    assert "Senior React Developer" in p and "react" in p
    for leaked in ("Candidate 101", "candidate_id", "secret summary", "90000", "headline"):
        assert leaked not in p


def test_prompt_wraps_data_between_tags_and_says_it_is_not_instructions():
    p = build_prompt(REQ, POOL)
    assert "<job_requirements>" in p and "</job_requirements>" in p
    assert "<candidate_pool>" in p and "</candidate_pool>" in p
    assert "never an" in p and "instruction" in p
    assert "Do NOT rank" in p


def test_prompt_keeps_null_as_null_and_handles_decimal():
    p = build_prompt(REQ, POOL)
    assert '"timezone_offsets": null' in p       # not stated stays null, never guessed
    assert '"years_experience": 7.5' in p        # Decimal became a number


def test_gemini_scorer_returns_valid_output():
    out = GeminiFitScorer(good_llm).score(REQ, POOL)
    assert out.fit_score == 92 and out.fit_reason


def test_gemini_scorer_sends_prompt_and_schema():
    seen = {}

    def spy(prompt, schema):
        seen["prompt"], seen["schema"] = prompt, schema
        return good_llm(prompt, schema)

    GeminiFitScorer(spy).score(REQ, POOL)
    assert "<job_requirements>" in seen["prompt"]
    assert set(seen["schema"]["properties"]) == {"fit_score", "fit_reason"}


@pytest.mark.parametrize("bad", [
    {"fit_score": 150, "fit_reason": "too high"},
    {"fit_score": -1, "fit_reason": "too low"},
    {"fit_score": 80, "fit_reason": ""},
    {"fit_score": 80, "fit_reason": "x" * 301},
    {"fit_score": 80},
    {"fit_score": 80, "fit_reason": "ok", "extra": "not allowed"},
])
def test_gemini_scorer_rejects_bad_answers(bad):
    scorer = GeminiFitScorer(lambda prompt, schema: json.dumps(bad))
    with pytest.raises(ValidationError):
        scorer.score(REQ, POOL)


def test_gemini_scorer_rejects_text_that_is_not_json():
    with pytest.raises(ValidationError):
        GeminiFitScorer(lambda prompt, schema: "I give it 100!").score(REQ, POOL)


def test_fake_scorer_fixed_and_per_title():
    fake = FakeFitScorer(default_score=70, scores_by_title={"Senior React Developer": 95})
    assert fake.score(REQ, POOL).fit_score == 95
    assert fake.score({"title": "Other"}, POOL).fit_score == 70
    assert [n for _, n in fake.calls] == [2, 2]
    