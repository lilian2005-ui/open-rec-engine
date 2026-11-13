from decimal import Decimal

import pytest

from backend.fit.scorer import FakeFitScorer, GeminiFitScorer, build_prompt, count_covering
from backend.llm import FakeLLM, LLMError

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
GOOD = {"fit_score": 92, "fit_reason": "Our pool has 1 profile with react."}


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


def test_prompt_has_the_score_guide_and_does_not_punish_a_small_pool():
    p = build_prompt(REQ, POOL)
    for band in ("90-100", "75-89", "60-74", "40-59", "1-39", "0: no profile"):
        assert band in p
    assert "size of the pool is NOT a reason" in p
    assert "never use it" in p                   # null (not stated) must not lower the score


DS = {"required_skills": ["python", "sql", "pandas"], "min_years_experience": 3}


def profile(skills, years):
    return {"skills": skills, "years_experience": years}


def test_count_covering_needs_ALL_required_skills():
    pool = [
        profile(["python", "sql", "pandas", "tableau"], 5),   # covers
        profile(["python", "sql", "airflow"], 6),             # no pandas -> does not cover
        profile(["python", "sql"], 4),                        # no pandas -> does not cover
    ]
    assert count_covering(DS, pool) == 1


def test_count_covering_checks_the_years():
    pool = [profile(["python", "sql", "pandas"], 2.5), profile(["python", "sql", "pandas"], 3)]
    assert count_covering(DS, pool) == 1                      # 3 years is enough, 2.5 is not


def test_count_covering_ignores_case_and_accepts_decimal():
    pool = [profile(["Python", " SQL ", "Pandas"], Decimal("4.5"))]
    assert count_covering(DS, pool) == 1


def test_count_covering_without_minimum_years_only_checks_skills():
    job = {"required_skills": ["react"], "min_years_experience": None}
    assert count_covering(job, [profile(["react"], None), profile(["vue"], 9)]) == 1


def test_count_covering_is_none_when_the_job_has_no_required_skills():
    assert count_covering({"required_skills": [], "min_years_experience": 3}, [profile(["x"], 5)]) is None


def test_prompt_gives_the_ai_the_count_made_by_the_code():
    pool = [profile(["python", "sql", "pandas"], 5), profile(["python", "sql"], 6)]
    p = build_prompt({"title": "Data Scientist", **DS}, pool)
    assert "1 profile(s) cover the job" in p
    assert "<system_count>" in p and "do not count again" in p


def test_prompt_says_the_count_is_missing_when_there_are_no_required_skills():
    p = build_prompt({"title": "X", "required_skills": []}, POOL)
    assert "not available for this job" in p


def test_prompt_keeps_null_as_null_and_handles_decimal():
    p = build_prompt(REQ, POOL)
    assert '"timezone_offsets": null' in p       # not stated stays null, never guessed
    assert '"years_experience": 7.5' in p        # Decimal became a number


def test_gemini_scorer_returns_valid_output():
    out = GeminiFitScorer(FakeLLM(GOOD)).score(REQ, POOL)
    assert out.fit_score == 92 and out.fit_reason


def test_gemini_scorer_sends_the_prompt_to_the_llm():
    fake = FakeLLM(GOOD)
    GeminiFitScorer(fake).score(REQ, POOL)
    assert fake.calls == 1
    assert fake.prompts[0] == build_prompt(REQ, POOL)


def test_gemini_scorer_asks_again_when_the_answer_is_bad():
    fake = FakeLLM({"fit_score": 150, "fit_reason": "too high"}, "{not json", GOOD)
    out = GeminiFitScorer(fake).score(REQ, POOL)
    assert out.fit_score == 92
    assert fake.calls == 3                       # 2 bad answers, then a good one


@pytest.mark.parametrize("bad", [
    {"fit_score": 150, "fit_reason": "too high"},
    {"fit_score": -1, "fit_reason": "too low"},
    {"fit_score": 80, "fit_reason": ""},
    {"fit_score": 80, "fit_reason": "x" * 301},
    {"fit_score": 80},
    {"fit_score": 80, "fit_reason": "ok", "extra": "not allowed"},
    "I give it 100!",                            # text that is not JSON
])
def test_gemini_scorer_gives_up_after_4_bad_answers(bad):
    fake = FakeLLM(bad, bad, bad, bad)
    with pytest.raises(LLMError) as err:
        GeminiFitScorer(fake).score(REQ, POOL)
    assert err.value.attempts == 4               # first call + 3 retries
    assert fake.calls == 4


def test_fake_scorer_fixed_and_per_title():
    fake = FakeFitScorer(default_score=70, scores_by_title={"Senior React Developer": 95})
    assert fake.score(REQ, POOL).fit_score == 95
    assert fake.score({"title": "Other"}, POOL).fit_score == 70
    assert [n for _, n in fake.calls] == [2, 2]