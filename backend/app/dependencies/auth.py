"""Authentication dependencies for protected API endpoints."""

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db


# Read the Bearer token from the Authorization header.
bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized_exception() -> HTTPException:
    """Return a consistent 401 response for authentication failures."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Validate the access token and return the active database user."""

    # 1. Check whether the request contains a Bearer token.
    if credentials is None:
        raise unauthorized_exception()

    # 2. Verify the JWT signature, expiration, and required claims.
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise unauthorized_exception() from None

    # 3. Retrieve the user from the database.
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    # 4. Reject missing or inactive accounts.
    if user is None or not user.is_active:
        raise unauthorized_exception()

    # 5. Return the authenticated database user.
    return user
