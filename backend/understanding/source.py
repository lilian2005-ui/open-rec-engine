"""Values Himalayas already gives in source_fields (decision A1).

When the source has a value, it is used and the LLM's value is ignored:
the source is exact, the LLM can guess. The LLM fills a field only when the
source has nothing for it.
"""
import math

from backend.schemas.enums import EmploymentType, SalaryPeriod, Seniority
from backend.schemas.job import JobRequirements

SENIORITY = {
    "entry-level": Seniority.ENTRY,
    "mid-level": Seniority.MID,
    "senior": Seniority.SENIOR,
    "manager": Seniority.LEAD,
    "director": Seniority.LEAD,
    "executive": Seniority.LEAD,
}

EMPLOYMENT = {
    "full time": EmploymentType.FULL_TIME,
    "part time": EmploymentType.PART_TIME,
    "contractor": EmploymentType.CONTRACTOR,
    "temporary": EmploymentType.OTHER,
    "intern": EmploymentType.OTHER,
    "other": EmploymentType.OTHER,
}


def _seniority(value) -> Seniority | None:
    """Himalayas sends a list, e.g. ["Senior"]. Only one clear level is used."""
    levels = {SENIORITY.get(str(v).strip().lower()) for v in (value or [])} - {None}
    return levels.pop() if len(levels) == 1 else None


def _employment(value) -> EmploymentType | None:
    return EMPLOYMENT.get(str(value).strip().lower()) if value else None


def _offsets(value) -> list[int]:
    """[-5, -4] stays as is. Half hours (-3.5) are rounded down (-4).
    Anything that is not a number is skipped."""
    out = set()
    for v in value or []:
        try:
            n = math.floor(float(v))
        except (TypeError, ValueError):
            continue
        if -12 <= n <= 14:
            out.add(n)
    return sorted(out)


def apply_source_fields(req: JobRequirements, source_fields: dict | None) -> JobRequirements:
    """Return a copy of the LLM answer where every value the source states wins."""
    sf = source_fields or {}
    updates = {}

    if sf.get("minSalary") is not None or sf.get("maxSalary") is not None:
        updates["salary_min"] = sf.get("minSalary")
        updates["salary_max"] = sf.get("maxSalary")
        updates["salary_currency"] = sf.get("currency")
        try:
            updates["salary_period"] = SalaryPeriod(sf.get("salaryPeriod"))
        except ValueError:
            updates["salary_period"] = None

    if offsets := _offsets(sf.get("timezoneRestrictions")):
        updates["timezone_offsets"] = offsets
    if seniority := _seniority(sf.get("seniority")):
        updates["seniority"] = seniority
    if employment := _employment(sf.get("employmentType")):
        updates["employment_type"] = employment

    # model_validate runs the schema checks again (e.g. salary_min <= salary_max)
    return JobRequirements.model_validate({**req.model_dump(), **updates})