"""Seed conversion checks. No database needed (the DB run is checked by hand, see PR)."""
from decimal import Decimal
from pathlib import Path

from backend.db.models.candidate import Candidate
from backend.db.models.enums import Seniority
from backend.db.seed_candidates import load_profiles, to_row_data

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "candidates.json"


def test_row_data_matches_the_candidate_columns():
    """If someone renames a column in the model or the schema, this fails."""
    columns = {c.name for c in Candidate.__table__.columns}
    for profile in load_profiles(DATA_FILE):
        assert set(to_row_data(profile)) == columns


def test_values_use_the_database_types():
    data = to_row_data(load_profiles(DATA_FILE)[0])
    assert isinstance(data["seniority"], Seniority)
    assert isinstance(data["years_experience"], Decimal)
    assert Candidate(**data).candidate_id == 101