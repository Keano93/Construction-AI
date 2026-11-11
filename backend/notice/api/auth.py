from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Organisation, User
from ..record import audit
from ..security import create_token, hash_password, verify_password
from .deps import current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    organisation: str = Field(min_length=2)
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _token_response(u: User, org: Organisation) -> dict:
    return {"token": create_token(str(u.id), str(u.org_id)),
            "user": {"id": str(u.id), "name": u.name, "email": u.email, "role": u.role, "organisation": org.name}}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none():
        raise HTTPException(409, "Email already registered")
    org = Organisation(name=body.organisation)
    db.add(org)
    db.flush()
    u = User(org_id=org.id, email=body.email.lower(), name=body.name, password_hash=hash_password(body.password), role="admin")
    db.add(u)
    db.flush()
    audit(db, action="user.register", actor_type="user", actor_id=str(u.id), org_id=org.id, entity_type="user", entity_id=u.id)
    db.commit()
    return _token_response(u, org)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if u is None or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Invalid email or password")
    audit(db, action="user.login", actor_type="user", actor_id=str(u.id), org_id=u.org_id, entity_type="user", entity_id=u.id)
    db.commit()
    return _token_response(u, db.get(Organisation, u.org_id))


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = db.get(Organisation, user.org_id)
    return {"id": str(user.id), "name": user.name, "email": user.email, "role": user.role, "organisation": org.name}
