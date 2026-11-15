"""P2-3: who may call the routes. These tests need no database: get_db gives None,
because the answer (401 / 403 / CORS) comes before any query."""
import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_current_user
from backend.api.main import app
from backend.db.models import AppUser
from backend.db.models.enums import UserRole
from backend.db.session import get_db

NEW_ROUTES = [
    ("GET", "/jobs"),
    ("GET", "/jobs/1"),
    ("GET", "/leads"),
    ("GET", "/leads/1"),
    ("PATCH", "/leads/1/contact"),
    ("POST", "/leads/1/draft/regenerate"),
    ("PATCH", "/drafts/1"),
    ("POST", "/drafts/1/approve"),
    ("POST", "/drafts/1/reject"),
    ("GET", "/settings"),
    ("PUT", "/settings"),
]


def _no_db():
    yield None


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _no_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("method, path", NEW_ROUTES)
def test_no_token_is_401(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.json() == {"detail": "Missing token"}


def test_every_new_route_is_in_the_list_above():
    """A route added later must be added to NEW_ROUTES, so it gets the 401 test."""
    known = {(m, p.replace("/1", "/{id}")) for m, p in NEW_ROUTES}
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith(("/jobs", "/leads", "/drafts", "/settings")):
            generic = path.replace("{job_id}", "{id}").replace("{lead_id}", "{id}") \
                          .replace("{draft_id}", "{id}")
            for method in route.methods - {"HEAD", "OPTIONS"}:
                assert (method, generic) in known, f"{method} {path} has no 401 test"


def test_reviewer_cannot_change_settings(client):
    app.dependency_overrides[get_current_user] = lambda: AppUser(
        user_id=1, full_name="Reviewer", email="r@example.com", role=UserRole.REVIEWER)
    response = client.put("/settings", json={"lead_threshold": 70})
    assert response.status_code == 403
    assert response.json() == {"detail": "Admin access required"}


def test_nothing_can_send_a_message():
    """FR-25: there is no send endpoint."""
    for route in app.routes:
        path = getattr(route, "path", "").lower()
        assert "send" not in path and "email" not in path and "mail" not in path, path


def test_frontend_origin_is_allowed_by_cors(client):
    response = client.options("/jobs", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_other_origins_are_not_allowed_by_cors(client):
    response = client.options("/jobs", headers={
        "Origin": "http://evil.example",
        "Access-Control-Request-Method": "GET",
    })
    assert "access-control-allow-origin" not in response.headers
