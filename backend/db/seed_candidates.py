"""Load data/candidates.json into the `candidate` table (FR-13, FR-14).

Run from the repo root (database must be up and migrated: `alembic upgrade head`):

    python -m backend.db.seed_candidates [path/to/candidates.json]

Rules:
  * All profiles are validated with CandidateProfile (P0-3) BEFORE anything is written.
  * Safe to run many times: new ids are added, changed ids are updated, same ids are untouched.
  * Rows that disappeared from the file are NOT deleted (FR-14 asks only to add/reload).
  * Only the `candidate` table is touched. ORM only, no hand-written SQL (NFR-06).
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from backend.db.models.candidate import Candidate
from backend.db.models.enums import Seniority
from backend.db.session import SessionLocal, get_engine
from backend.schemas.candidate import CandidateProfile

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "candidates.json"


def load_profiles(path: Path) -> list[CandidateProfile]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    profiles = [CandidateProfile.model_validate(item) for item in raw]  # stops on the first bad item
    ids = [p.candidate_id for p in profiles]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate candidate_id in file")
    return profiles


def to_row_data(profile: CandidateProfile) -> dict:
    """Schema object -> values for the Candidate model (the DB uses its own enum and Decimal)."""
    data = profile.model_dump(mode="json")  # enums become plain strings
    if data["years_experience"] is not None:
        data["years_experience"] = Decimal(str(data["years_experience"]))
    if data["seniority"] is not None:
        data["seniority"] = Seniority(data["seniority"])
    return data


def seed(session: Session, profiles: list[CandidateProfile]) -> dict:
    added = updated = unchanged = 0
    for profile in profiles:
        data = to_row_data(profile)
        row = session.get(Candidate, profile.candidate_id)
        if row is None:
            session.add(Candidate(**data))
            added += 1
            continue
        changed = False
        for key, value in data.items():
            if getattr(row, key) != value:
                setattr(row, key, value)
                changed = True
        updated += changed
        unchanged += not changed
    session.commit()
    return {"added": added, "updated": updated, "unchanged": unchanged}


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    profiles = load_profiles(path)
    with SessionLocal(bind=get_engine()) as session:
        print("candidates.json -> candidate table:", seed(session, profiles))


if __name__ == "__main__":
    main()