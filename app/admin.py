from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app import guard
from app.auth import allowed_styles, is_admin, require_admin, revoke_sessions
from app.config import get_settings
from app.db import session
from app.models import STYLES, User, parse_styles

router = APIRouter(prefix="/api/admin")


class AccessInput(BaseModel):
    active: bool


class CreditsInput(BaseModel):
    credits_day: int | None = Field(None, ge=0, le=1_000_000)


class StylesInput(BaseModel):
    styles: list[str] = Field(max_length=len(STYLES))

    @field_validator("styles")
    @classmethod
    def known_styles(cls, value):
        unknown = [s for s in value if str(s).strip().lower() not in STYLES]
        if unknown:
            raise ValueError(f"Unknown style {unknown[0]!r}. Use " + ", ".join(STYLES) + ".")
        picked = parse_styles(value)
        if not picked:
            raise ValueError("Give at least one style.")
        return picked


@router.get("/users")
def users(admin: User = Depends(require_admin)):
    s = get_settings()
    used = guard.user_usage()
    with session() as db:
        people = list(db.scalars(select(User).order_by(User.email)))
    return {
        "credits_user_day": s.credits_user_day,
        "credits_anon_day": s.credits_anon_day,
        "site": guard.summary(),
        "styles": list(STYLES),
        "users": [
            {"id": u.id, "email": u.email, "name": u.name, "active": u.active, "is_admin": is_admin(u), "me": u.id == admin.id,
             "credits_day": guard.limit_for(u), "credits_own": u.credits_day is not None,
             "styles": allowed_styles(u),
             "used_today": used.get(u.id, {}).get("today", 0), "used_week": used.get(u.id, {}).get("week", 0),
             "created": u.created, "last_seen": u.last_seen}
            for u in people
        ],
    }


@router.patch("/users/{user_id}")
def set_access(user_id: str, body: AccessInput, admin: User = Depends(require_admin)):
    with session() as db, db.begin():
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, detail="Account not found.")
        if is_admin(target):
            raise HTTPException(400, detail="The administrator cannot be blocked here.")
        target.active = body.active
        if not body.active:
            revoke_sessions(db, user_id)
    return {"ok": True, "active": body.active}


@router.patch("/users/{user_id}/credits")
def set_credits(user_id: str, body: CreditsInput, admin: User = Depends(require_admin)):
    with session() as db, db.begin():
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, detail="Account not found.")
        target.credits_day = body.credits_day
    return {"ok": True, "credits_day": guard.limit_for(target)}


@router.patch("/users/{user_id}/styles")
def set_styles(user_id: str, body: StylesInput, admin: User = Depends(require_admin)):
    with session() as db, db.begin():
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, detail="Account not found.")
        if is_admin(target):
            raise HTTPException(400, detail="The administrator always has every style.")
        target.styles = ",".join(body.styles)
    return {"ok": True, "styles": body.styles}
