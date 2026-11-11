"""Load default app settings into the app_setting table.
Only missing keys are added; values an admin changed are never overwritten.
Run:  python -m backend.db.seed_settings
"""
from datetime import datetime, timezone

from sqlalchemy import select

from backend.db.models import AppSetting
from backend.db.session import SessionLocal, get_engine
from backend.schemas.settings import AppSettings


def seed_settings(session) -> list[str]:
    existing = set(session.scalars(select(AppSetting.key)))
    added = []
    for key, value in AppSettings().to_rows():
        if key not in existing:
            session.add(AppSetting(key=key, value=value, updated_at=datetime.now(timezone.utc)))
            added.append(key)
    session.commit()
    return added


if __name__ == "__main__":
    with SessionLocal(bind=get_engine()) as session:
        added = seed_settings(session)
        print(f"added: {added}" if added else "all settings already exist, nothing changed")