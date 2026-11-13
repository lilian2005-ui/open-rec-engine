"""Auth routes: register, login."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models.app_user import AppUser
from backend.schemas.auth import UserRegister, UserLogin, UserOut, TokenOut
from backend.api.security import hash_password, verify_password, create_token
from backend.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

# Fixed dummy hash for constant-time comparison when email is not found
_DUMMY_HASH = hash_password("dummy-timing-pad")


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: UserRegister, db: Session = Depends(get_db)):
    user = AppUser(
        full_name=body.full_name,
        email=body.email,  # schema already lowercases it
        password_hash=hash_password(body.password),
        # role is not accepted from the request — model default is 'reviewer'
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already registered")
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(AppUser).filter(AppUser.email == body.email.lower()).first()

    if not user:
        # Run verify anyway so response time stays roughly the same
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(401, "Invalid email or password")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    if not user.is_active:
        raise HTTPException(401, "Invalid email or password")

    token = create_token(user.user_id, user.role)
    return TokenOut(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserOut)
def me(user: AppUser = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return user
