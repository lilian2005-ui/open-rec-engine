"""Register, login and user data (FR-35 to FR-37). Passwords never leave the API."""
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from .common import Schema
from .enums import UserRole


class UserRegister(Schema):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)   # bcrypt uses at most 72 bytes

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()                                  # app_user.email is unique in lowercase

    @field_validator("password")
    @classmethod
    def _strong(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("password is too long")
        if v.isdigit() or v.isalpha():
            raise ValueError("password must contain letters and numbers")
        return v


class UserLogin(Schema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserOut(Schema):
    """What the API returns about a user. There is no password field on purpose."""

    user_id: int
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class TokenOut(Schema):
    access_token: str
    token_type: str = "bearer"
