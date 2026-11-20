"""create_admin CLI: input/getpass are replaced with ready answers, and the script's
own session is replaced with the test `db` session (rolled back after each test)."""
import pytest
from sqlalchemy import select

from backend.api.security import verify_password
from backend.db import create_admin
from backend.db.models.app_user import AppUser

PASSWORD = "Strong123"


@pytest.fixture
def run(db, monkeypatch):
    """run(name, email, password, confirm=None) runs create_admin.main() with these answers."""
    monkeypatch.setattr(create_admin, "get_engine", lambda: None)
    monkeypatch.setattr(create_admin, "SessionLocal", lambda **kw: db)
    monkeypatch.setattr(db, "close", lambda: None)      # main() closes it, the test still needs it

    def _run(name, email, password, confirm=None):
        answers = iter([name, email])
        passwords = iter([password, password if confirm is None else confirm])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        monkeypatch.setattr("getpass.getpass", lambda _: next(passwords))
        create_admin.main()
    return _run


def users_with(db, email):
    return db.scalars(select(AppUser).where(AppUser.email == email)).all()


def test_creates_an_admin(db, run):
    run("Shaima Test", "Admin@Test.com", PASSWORD)
    [user] = users_with(db, "admin@test.com")          # email is saved in lowercase
    assert user.role == "admin"
    assert user.full_name == "Shaima Test"


def test_password_is_hashed(db, run):
    run("Shaima Test", "admin@test.com", PASSWORD)
    [user] = users_with(db, "admin@test.com")
    assert user.password_hash != PASSWORD
    assert verify_password(PASSWORD, user.password_hash)


def test_existing_email_is_rejected(db, run):
    run("Shaima Test", "admin@test.com", PASSWORD)
    with pytest.raises(SystemExit) as exit_:
        run("Other Name", "ADMIN@test.com", PASSWORD)  # same email, other case
    assert exit_.value.code == 1
    assert len(users_with(db, "admin@test.com")) == 1


@pytest.mark.parametrize("password, confirm", [
    ("abc12", None),          # too short (< 8)
    ("abcdefgh", None),       # letters only
    ("12345678", None),       # numbers only
    (PASSWORD, "Other123"),   # confirm does not match
])
def test_bad_password_is_rejected(db, run, password, confirm):
    with pytest.raises(SystemExit) as exit_:
        run("Shaima Test", "admin@test.com", password, confirm)
    assert exit_.value.code == 1
    assert users_with(db, "admin@test.com") == []