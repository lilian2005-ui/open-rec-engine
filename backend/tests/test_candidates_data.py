"""Checks data/candidates.json against the data contract (P0-4, FR-13).

Run:  python -m pytest backend/tests/test_candidates_data.py -v
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.candidate import CandidateProfile

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "candidates.json"
MIN_PROFILES = 30


@pytest.fixture(scope="module")
def raw() -> list[dict]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def profiles(raw) -> list[CandidateProfile]:
    return [CandidateProfile.model_validate(item) for item in raw]


def _find(profiles, skills, min_years=0, tz=None):
    need = set(skills)
    return [
        p.candidate_id
        for p in profiles
        if need <= set(p.skills)
        and p.years_experience >= min_years
        and (tz is None or tz in p.timezone_offsets)
    ]


def test_at_least_30_profiles(raw):
    assert len(raw) >= MIN_PROFILES


def test_every_profile_passes_the_schema(raw):
    errors = []
    for item in raw:
        try:
            CandidateProfile.model_validate(item)
        except ValidationError as e:
            errors.append(f"id={item.get('candidate_id')}: {e.errors()[0]['msg']}")
    assert not errors, "\n".join(errors)


def test_candidate_ids_are_unique(profiles):
    ids = [p.candidate_id for p in profiles]
    assert len(ids) == len(set(ids))


def test_skills_are_already_canonical(raw, profiles):
    """The schema normalises skills; the file must already be in that form."""
    for item, p in zip(raw, profiles):
        assert item["skills"] == p.skills, f"id={p.candidate_id}: skills change after normalisation"


def test_every_profile_has_a_timezone(profiles):
    for p in profiles:
        assert p.timezone_offsets, f"id={p.candidate_id}: no timezone"
        assert all(-12 <= t <= 14 for t in p.timezone_offsets), f"id={p.candidate_id}: bad offset"


def test_seniority_matches_years(profiles):
    for p in profiles:
        level = getattr(p.seniority, "value", p.seniority)
        if level == "entry":
            assert p.years_experience <= 2.5, f"id={p.candidate_id}"
        if level == "senior":
            assert p.years_experience >= 4, f"id={p.candidate_id}"
        if level == "lead":
            assert p.years_experience >= 8, f"id={p.candidate_id}"


def test_pool_covers_the_demo_cases(profiles):
    """Guards the report's examples. Loosen on purpose if you change the pool."""
    assert len(_find(profiles, ["react", "typescript", "redux"], 5, -5)) == 3   # Acme: 'fit 92'
    assert len(_find(profiles, ["python", "fastapi", "postgresql"])) >= 2        # Orbit Tech
    assert len(_find(profiles, ["pytorch", "nlp"])) >= 2                         # Helix AI
    assert _find(profiles, ["kubernetes"], 5) == []                              # Brightly: low fit