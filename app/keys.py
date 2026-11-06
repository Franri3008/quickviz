from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.auth import current_user, new_key
from app.db import session
from app.models import ApiKey, User

MAX_KEYS = 10
router = APIRouter(prefix="/api/keys")


class KeyInput(BaseModel):
    name: str = Field("", max_length=60)


def shown(key: ApiKey) -> dict:
    return {"id": key.id, "name": key.name, "prefix": key.prefix, "created": key.created, "last_used": key.last_used}


@router.get("")
def list_keys(user: User = Depends(current_user)):
    with session() as db:
        keys = db.scalars(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created.desc()))
        return {"keys": [shown(k) for k in keys], "max": MAX_KEYS}


@router.post("")
def create_key(body: KeyInput, user: User = Depends(current_user)):
    name = " ".join(body.name.split())[:60] or "Claude"
    with session() as db, db.begin():
        have = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user.id)) or 0
        if have >= MAX_KEYS:
            raise HTTPException(400, detail=f"You can have at most {MAX_KEYS} keys. Delete one first.")
        token, prefix, hashed = new_key()
        key = ApiKey(user_id=user.id, name=name, prefix=prefix, digest=hashed)
        db.add(key)
        db.flush()
        return {**shown(key), "key": token}


@router.delete("/{key_id}")
def revoke_key(key_id: str, user: User = Depends(current_user)):
    with session() as db, db.begin():
        key = db.get(ApiKey, key_id)
        if not key or key.user_id != user.id:
            raise HTTPException(404, detail="Key not found.")
        db.delete(key)
    return {"ok": True}
