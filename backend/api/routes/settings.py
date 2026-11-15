"""Settings routes (P2-6): read for everyone, change for admins. Secrets stay in .env."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, require_admin
from backend.api.schemas import SettingsOut, SettingsUpdate
from backend.db.models import AppSetting, AppUser
from backend.db.session import get_db
from backend.discovery.service import load_settings
from backend.schemas.settings import AppSettings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut, dependencies=[Depends(get_current_user)])
def get_settings(db: Session = Depends(get_db)):
    return load_settings(db)


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db),
                    admin: AppUser = Depends(require_admin)):
    """Change only the fields that are sent. A value outside the limits of
    AppSettings is answered with 422."""
    current = load_settings(db)
    try:
        new = AppSettings.model_validate(
            {**current.model_dump(), **body.model_dump(exclude_unset=True)})
    except ValidationError as exc:
        raise RequestValidationError(exc.errors())

    old = dict(current.to_rows())
    now = datetime.now(timezone.utc)
    for key, value in new.to_rows():
        if value != old[key]:
            # merge: updates the row of this key (or adds it if the table lacks it)
            db.merge(AppSetting(key=key, value=value, updated_by=admin.user_id, updated_at=now))
    db.commit()
    return new
