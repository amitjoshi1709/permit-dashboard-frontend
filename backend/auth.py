"""
Simple shared-credential authentication.

One username + password is configured in .env. Successful login returns a
signed JWT token. All protected API routes require a valid bearer token.
"""
import os
import time
from typing import Optional

import jwt
from fastapi import HTTPException, Header

TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


def _get_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise HTTPException(500, "JWT_SECRET not configured on server")
    return secret


def verify_credentials(username: str, password: str) -> bool:
    expected_user = os.getenv("DASHBOARD_USERNAME", "")
    expected_pass = os.getenv("DASHBOARD_PASSWORD", "")
    if not expected_user or not expected_pass:
        raise HTTPException(500, "Dashboard credentials not configured on server")
    return username == expected_user and password == expected_pass


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, _get_secret(), algorithm="HS256")


def require_auth(authorization: Optional[str] = Header(None)) -> str:
    """FastAPI dependency — raises 401 if the request lacks a valid token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
        return payload.get("sub", "")
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
