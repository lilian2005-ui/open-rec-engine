"""Password hashing (bcrypt) and JWT helpers."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from backend.config import settings


# ── Password ────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    pwd_bytes = password.encode("utf-8")
    # bcrypt يقرأ بس أول 72 byte — الـ schema أصلاً بيمنع أطول من 72
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Compare a plaintext password against a bcrypt hash.
    Returns False (instead of crashing) if the password exceeds 72 bytes."""
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        return False
    try:
        return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT ─────────────────────────────────────────────────

def _secret() -> str:
    """Return the JWT secret, refusing weak or missing values."""
    s = settings.JWT_SECRET
    if not s or s == "change-me" or len(s) < 32:
        raise RuntimeError(
            "JWT_SECRET is missing, too short (< 32 chars), or still 'change-me'."
        )
    return s


def create_token(user_id: int, role: str) -> str:
    """Create a signed JWT with sub (as string), role, iat, and exp."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),   # ← دائماً string
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def read_token(token: str) -> int | None:
    """Decode a JWT and return the user_id, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
        return int(payload["sub"])
    except Exception:
        return None