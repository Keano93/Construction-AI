import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project, User
from ..security import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from None
    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def project_for(project_id: uuid.UUID, user: User, db: Session) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return p


def owned(obj, user: User, db: Session):
    """404 unless `obj` belongs to a project in the user's organisation."""
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    project_for(obj.project_id, user, db)
    return obj
