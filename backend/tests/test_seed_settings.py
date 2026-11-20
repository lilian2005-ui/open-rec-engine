"""seed_settings: fills missing app_setting keys and never overwrites an admin's value.
The migrations already seed the defaults, so each test clears rows first."""
from sqlalchemy import delete, select

from backend.db.models import DEFAULT_SETTINGS, AppSetting
from backend.db.seed_settings import seed_settings


def all_rows(db) -> dict[str, str]:
    return {r.key: r.value for r in db.scalars(select(AppSetting))}


def test_empty_table_gets_every_default(db):
    db.execute(delete(AppSetting))
    added = seed_settings(db)
    assert set(added) == set(DEFAULT_SETTINGS)
    assert all_rows(db) == DEFAULT_SETTINGS     # same keys and same values as the migration


def test_running_twice_adds_nothing(db):
    db.execute(delete(AppSetting))
    seed_settings(db)
    assert seed_settings(db) == []
    assert len(all_rows(db)) == len(DEFAULT_SETTINGS)


def test_only_missing_keys_are_added(db):
    db.execute(delete(AppSetting).where(AppSetting.key == "fetch_limit"))
    assert seed_settings(db) == ["fetch_limit"]


def test_admin_value_is_kept(db):
    db.get(AppSetting, "lead_threshold").value = "75"
    db.flush()
    seed_settings(db)
    assert db.get(AppSetting, "lead_threshold").value == "75"