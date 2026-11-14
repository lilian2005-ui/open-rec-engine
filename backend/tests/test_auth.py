"""Tests for P2-7 Authentication."""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.db.session import get_engine, SessionLocal
from backend.db.models.app_user import AppUser
from backend.api.security import hash_password, verify_password, create_token, read_token


@pytest.fixture()
def db():
    """One DB session per test, rolled back at the end."""
    connection = get_engine().connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """TestClient with the DB session overridden."""
    from backend.db.session import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


# ─── 1. Security helpers ──────────────────────────

def test_hash_and_verify():
    h = hash_password("MyStr0ng!Pass")
    assert h.startswith("$2")
    assert verify_password("MyStr0ng!Pass", h) is True
    assert verify_password("wrong", h) is False


def test_verify_long_password_returns_false():
    """Passwords over 72 bytes should return False, not crash."""
    h = hash_password("short")
    long_pw = "a" * 100
    assert verify_password(long_pw, h) is False


def test_token_roundtrip():
    token = create_token(42, "reviewer")
    assert read_token(token) == 42


def test_expired_token_returns_none():
    """A token with exp in the past should return None."""
    from datetime import datetime, timedelta, timezone
    import jwt as pyjwt
    from backend.api.security import _secret

    payload = {
        "sub": "1",
        "role": "reviewer",
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = pyjwt.encode(payload, _secret(), algorithm="HS256")
    assert read_token(token) is None


def test_bad_signature_returns_none():
    import jwt as pyjwt
    from datetime import datetime, timedelta, timezone

    payload = {
        "sub": "1",
        "role": "reviewer",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
    assert read_token(token) is None



# ─── 2. Register ───────────────────────────────────

def test_register_success(client, db):
    res = client.post("/auth/register", json={
        "full_name": "Test User",
        "email": "new@example.com",
        "password": "MyStr0ng!1",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "new@example.com"
    assert data["role"] == "reviewer"

    # Hash in DB starts with $2 (bcrypt)
    user = db.query(AppUser).filter(AppUser.email == "new@example.com").first()
    assert user.password_hash.startswith("$2")


def test_register_duplicate_case_insensitive(client):
    client.post("/auth/register", json={
        "full_name": "First",
        "email": "Dup@Example.com",
        "password": "MyStr0ng!1",
    })
    res = client.post("/auth/register", json={
        "full_name": "Second",
        "email": "dup@example.com",
        "password": "MyStr0ng!1",
    })
    assert res.status_code == 409


# ─── 3. Login ──────────────────────────────────────

def _create_user(db, email="login@example.com", password="MyStr0ng!1", active=True):
    user = AppUser(
        full_name="Login Test",
        email=email,
        password_hash=hash_password(password),
        is_active=active,
    )
    db.add(user)
    db.flush()
    return user


def test_login_success(client, db):
    _create_user(db)
    res = client.post("/auth/login", json={
        "email": "login@example.com",
        "password": "MyStr0ng!1",
    })
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(client, db):
    _create_user(db)
    res = client.post("/auth/login", json={
        "email": "login@example.com",
        "password": "WrongPass!1",
    })
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid email or password"


def test_login_email_not_found(client):
    res = client.post("/auth/login", json={
        "email": "nobody@example.com",
        "password": "Whatever!1",
    })
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid email or password"


def test_login_inactive_user(client, db):
    _create_user(db, active=False)
    res = client.post("/auth/login", json={
        "email": "login@example.com",
        "password": "MyStr0ng!1",
    })
    assert res.status_code == 401


def test_login_long_arabic_password(client, db):
    """Arabic password at 72 chars (>72 bytes in UTF-8) should return 401, not 500."""
    _create_user(db)
    # 72 Arabic chars = 144 bytes UTF-8, but schema max_length is 72 chars
    # So we use 36 chars (72 bytes) which passes schema but hits bcrypt limit
    long_pw = "ك" * 36  # exactly 72 bytes in UTF-8
    res = client.post("/auth/login", json={
        "email": "login@example.com",
        "password": long_pw,
    })
    assert res.status_code == 401




# ─── 4. /auth/me ───────────────────────────────────

def _auth_header(user_id, role="reviewer"):
    token = create_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


def test_me_with_valid_token(client, db):
    user = _create_user(db, email="me@example.com")
    res = client.get("/auth/me", headers=_auth_header(user.user_id))
    assert res.status_code == 200
    assert res.json()["email"] == "me@example.com"


def test_me_without_token(client):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_me_bad_token(client):
    res = client.get("/auth/me", headers={"Authorization": "Bearer fake.token.here"})
    assert res.status_code == 401


def test_me_no_bearer_prefix(client):
    token = create_token(1, "reviewer")
    res = client.get("/auth/me", headers={"Authorization": token})
    assert res.status_code == 401


def test_me_inactive_user_after_token(client, db):
    """User gets deactivated after token was issued."""
    user = _create_user(db, email="deact@example.com")
    headers = _auth_header(user.user_id)
    user.is_active = False
    db.flush()
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 401


# ─── 5. require_admin ─────────────────────────────

def test_reviewer_on_admin_route(client, db):
    """A reviewer hitting an admin-only route should get 403."""
    from fastapi import Depends
    from backend.api.deps import require_admin

    # Temporary admin-only route for testing
    @app.get("/test-admin-only")
    def _admin_only(user=Depends(require_admin)):
        return {"ok": True}

    user = _create_user(db, email="rev@example.com")
    res = client.get("/test-admin-only", headers=_auth_header(user.user_id))
    assert res.status_code == 403


def test_admin_on_admin_route(client, db):
    user = _create_user(db, email="adm@example.com")
    user.role = "admin"
    db.flush()
    res = client.get("/test-admin-only", headers=_auth_header(user.user_id, "admin"))
    assert res.status_code == 200    