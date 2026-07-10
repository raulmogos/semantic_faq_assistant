"""
JWT bearer token authentication utilities and FastAPI dependency.

Flow:
  POST /auth/register  →  creates user, returns token
  POST /auth/login     →  verifies credentials, returns token
  Any protected route  →  extracts token from Authorization: Bearer <token>
                          resolves the current User via get_current_user()
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.settings import get_settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer()


def create_access_token(user_id: int) -> str:
    """Create a signed JWT token for the given user_id."""
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """
    Decode and validate a JWT token.
    Returns the user_id (int) on success.
    Raises HTTPException 401 on any failure.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return int(payload["sub"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired."
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}"
        ) from exc


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> Any:
    """
    FastAPI dependency that resolves the authenticated User from the bearer token.
    Inject with: current_user: User = Depends(get_current_user)
    """
    user_id = decode_access_token(credentials.credentials)
    user = await request.app.state.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user
