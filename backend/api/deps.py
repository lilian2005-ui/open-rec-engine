"""FastAPI dependencies: current user and role checks."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models.app_user import AppUser
from backend.api.security import read_token

# auto_error=False so we return 401 instead of FastAPI's default 403
_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_scheme),
    db: Session = Depends(get_db),
) -> AppUser:
    """Return the authenticated user or raise 401."""
    if not creds:
        raise HTTPException(401, "Missing token", headers={"WWW-Authenticate": "Bearer"})

    user_id = read_token(creds.credentials)
    if user_id is None:
        raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})

    user = db.get(AppUser, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive", headers={"WWW-Authenticate": "Bearer"})

    return user


def require_admin(user: AppUser = Depends(get_current_user)) -> AppUser:
    """Allow only admin users; role is checked from DB, not the token."""
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user