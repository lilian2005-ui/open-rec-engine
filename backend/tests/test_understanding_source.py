"""Tests for decision A1: values from Himalayas (source_fields) win over the LLM."""
from backend.schemas.enums import EmploymentType, SalaryPeriod, Seniority
from backend.schemas.job import JobRequirements
from backend.understanding.source import apply_source_fields

AI = JobRequirements(title="React Developer", required_skills=["react"],
                     seniority="mid", timezone_offsets=[0, 1], employment_type=None)


def test_source_values_replace_the_ai_values():
    sf = {"seniority": ["Senior"], "employmentType": "Full Time", "timezoneRestrictions": [-5, -4],
          "minSalary": 90000, "maxSalary": 120000, "currency": "USD", "salaryPeriod": "annual"}
    out = apply_source_fields(AI, sf)
    assert out.seniority == Seniority.SENIOR
    assert out.employment_type == EmploymentType.FULL_TIME
    assert out.timezone_offsets == [-5, -4]
    assert (out.salary_min, out.salary_max, out.salary_currency) == (90000, 120000, "USD")
    assert out.salary_period == SalaryPeriod.ANNUAL


def test_no_source_fields_keeps_the_ai_answer():
    assert apply_source_fields(AI, None) == AI
    assert apply_source_fields(AI, {}) == AI


def test_salary_period_alone_does_not_add_a_salary():
    out = apply_source_fields(AI, {"salaryPeriod": "annual"})   # Himalayas sends it even without a salary
    assert out.salary_min is None and out.salary_period is None


def test_half_hour_offsets_are_rounded_down_and_junk_is_skipped():
    out = apply_source_fields(AI, {"timezoneRestrictions": [-4, -3.5, "x", None]})
    assert out.timezone_offsets == [-4]


def test_several_seniority_levels_keep_the_ai_value():
    out = apply_source_fields(AI, {"seniority": ["Mid-level", "Senior"]})
    assert out.seniority == Seniority.MID


def test_director_and_executive_become_lead():
    assert apply_source_fields(AI, {"seniority": ["Director"]}).seniority == Seniority.LEAD
    assert apply_source_fields(AI, {"seniority": ["Executive"]}).seniority == Seniority.LEAD


def test_unknown_employment_type_keeps_the_ai_value():
    assert apply_source_fields(AI, {"employmentType": "Volunteer"}).employment_type is None