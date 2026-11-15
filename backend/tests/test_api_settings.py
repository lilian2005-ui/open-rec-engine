"""P2-3: GET /settings and PUT /settings. Real PostgreSQL (``db`` of conftest.py);
the app_setting rows are the defaults seeded by the migrations."""
from backend.db.models import AppSetting
from backend.discovery.service import load_settings
from backend.tests.api_fixtures import admin, client, reviewer  # noqa: F401

DEFAULTS = {"lead_threshold": 60, "fetch_limit": 100, "himalayas_enabled": True,
            "run_mode": "manual", "max_retries": 3, "run_interval_hours": 32}


def row(db, key: str) -> AppSetting:
    return db.get(AppSetting, key)


def test_any_user_reads_the_settings_without_remotive(client, reviewer, db):
    response = client.get("/settings")

    assert response.status_code == 200
    assert response.json() == DEFAULTS      # exactly these keys: no remotive_enabled, no secrets


def test_admin_changes_only_the_sent_field(client, admin, db):
    before = row(db, "fetch_limit").updated_at

    response = client.put("/settings", json={"lead_threshold": 70})

    assert response.status_code == 200
    assert response.json() == {**DEFAULTS, "lead_threshold": 70}
    changed = row(db, "lead_threshold")
    assert changed.value == "70"
    assert changed.updated_by == admin.user_id
    assert changed.updated_at is not None
    # the other rows are not touched
    assert row(db, "fetch_limit").updated_at == before
    assert row(db, "fetch_limit").updated_by is None
    assert row(db, "remotive_enabled").value == "true"
    assert load_settings(db).lead_threshold == 70


def test_values_are_stored_as_lowercase_text(client, admin, db):
    response = client.put("/settings", json={"run_mode": "scheduled", "himalayas_enabled": False,
                                             "max_retries": 5})

    assert response.json() == {**DEFAULTS, "run_mode": "scheduled", "himalayas_enabled": False,
                               "max_retries": 5}
    assert row(db, "run_mode").value == "scheduled"
    assert row(db, "himalayas_enabled").value == "false"
    assert row(db, "max_retries").value == "5"


def test_a_value_outside_the_limits_is_422_and_saves_nothing(client, admin, db):
    for body in ({"lead_threshold": 150}, {"fetch_limit": 0}, {"max_retries": 6},
                 {"lead_threshold": 70, "max_retries": -1}, {"lead_threshold": None}):
        assert client.put("/settings", json=body).status_code == 422, body

    assert row(db, "lead_threshold").value == "60"
    assert client.get("/settings").json() == DEFAULTS


def test_run_interval_hours_is_saved_and_checked(client, admin, db):
    response = client.put("/settings", json={"run_interval_hours": 24})

    assert response.status_code == 200
    assert response.json() == {**DEFAULTS, "run_interval_hours": 24}
    assert row(db, "run_interval_hours").value == "24"
    for hours in (0, 169):
        assert client.put("/settings", json={"run_interval_hours": hours}).status_code == 422
    assert row(db, "run_interval_hours").value == "24"


def test_remotive_and_unknown_fields_are_rejected(client, admin, db):
    assert client.put("/settings", json={"remotive_enabled": False}).status_code == 422
    assert client.put("/settings", json={"gemini_api_key": "x"}).status_code == 422
    assert row(db, "remotive_enabled").value == "true"
