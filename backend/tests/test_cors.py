"""CORS: only the frontend address may call the API from a browser."""

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.config import settings

client = TestClient(app)


def _preflight(origin: str):
    """What the browser sends before a cross-origin POST."""
    return client.options("/auth/login", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })


def test_frontend_origin_allowed():
    origin = settings.CORS_ORIGINS[0]
    res = _preflight(origin)
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == origin


def test_other_origin_blocked():
    res = _preflight("http://evil.example.com")
    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers


def test_no_wildcard_origin():
    assert "*" not in settings.CORS_ORIGINS
