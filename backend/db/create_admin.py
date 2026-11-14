"""CLI script to create the first admin user."""

import getpass
import sys

from backend.config import settings  # noqa: F401 — triggers .env load
from backend.db.session import SessionLocal, get_engine
from backend.db.models.app_user import AppUser
from backend.schemas.auth import UserRegister
from backend.api.security import hash_password


def main():
    print("=== Create Admin User ===\n")

    full_name = input("Full name: ").strip()
    email = input("Email: ").strip()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("\nError: passwords do not match.")
        sys.exit(1)

    # Validate through the same schema as /auth/register
    try:
        validated = UserRegister(full_name=full_name, email=email, password=password)
    except Exception as e:
        print(f"\nValidation error: {e}")
        sys.exit(1)

    db = SessionLocal(bind=get_engine())
    try:
        exists = db.query(AppUser).filter(AppUser.email == validated.email).first()
        if exists:
            print(f"\nError: email {validated.email} already exists.")
            sys.exit(1)

        user = AppUser(
            full_name=validated.full_name,
            email=validated.email,
            password_hash=hash_password(validated.password),
            role="admin",
        )
        db.add(user)
        db.commit()
        print(f"\nAdmin created: {user.email} (id={user.user_id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()