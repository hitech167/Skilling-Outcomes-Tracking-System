"""
Lightweight JWT authentication + role checks.

Deliberately small: two roles, users configured through environment
variables (no users table, no registration, no refresh tokens).

    admin    -> manages trainee / training / outcome / follow-up /
                employment / verification / wage / status records
                (personal data), and can also read analytics/insights
    analyst  -> aggregated analytics and insights only (no PII)

Required environment variables (see .env.example):

    JWT_SECRET_KEY        at least 32 characters, random
    ADMIN_USERNAME / ADMIN_PASSWORD
    ANALYST_USERNAME / ANALYST_PASSWORD   (optional — omit to disable)
    JWT_EXPIRE_MINUTES    optional, default 60

Fails closed: if JWT_SECRET_KEY is missing/too short, no token can be
issued or accepted, so protected endpoints stay locked.
"""

import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

ROLE_ADMIN = "admin"
ROLE_ANALYST = "analyst"
JWT_ALGORITHM = "HS256"
MIN_SECRET_LENGTH = 32

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def _secret_key() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on the server.",
        )
    return secret


def _expire_minutes() -> int:
    try:
        return max(1, int(os.getenv("JWT_EXPIRE_MINUTES", "60")))
    except ValueError:
        return 60


def _configured_users() -> dict:
    """username -> (password, role), read from the environment on each call."""
    users = {}
    for role, prefix in ((ROLE_ADMIN, "ADMIN"), (ROLE_ANALYST, "ANALYST")):
        username = os.getenv(f"{prefix}_USERNAME", "").strip()
        password = os.getenv(f"{prefix}_PASSWORD", "")
        if username and password:
            users[username] = (password, role)
    return users


def authenticate(username: str, password: str) -> str | None:
    """Return the user's role if the credentials match, otherwise None."""
    entry = _configured_users().get(username.strip())
    if entry is None:
        # Still do a comparison so response time doesn't reveal valid usernames.
        hmac.compare_digest(password.encode(), b"-" * max(len(password), 1))
        return None
    expected_password, role = entry
    if hmac.compare_digest(password.encode(), expected_password.encode()):
        return role
    return None


def create_access_token(username: str, role: str) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    minutes = _expire_minutes()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, _secret_key(), algorithm=JWT_ALGORITHM), minutes * 60


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            _secret_key(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.PyJWTError:
        raise unauthorized

    role = payload.get("role")
    if role not in (ROLE_ADMIN, ROLE_ANALYST):
        raise unauthorized
    # The user must still be configured with the same role (revocation by
    # removing/changing the env entry).
    entry = _configured_users().get(payload["sub"])
    if entry is None or entry[1] != role:
        raise unauthorized
    return {"username": payload["sub"], "role": role}


def require_roles(*roles: str):
    """FastAPI dependency factory: allow only the given roles."""

    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return user

    return _check


require_admin = require_roles(ROLE_ADMIN)
require_analytics_access = require_roles(ROLE_ADMIN, ROLE_ANALYST)


# ---------------------------------------------------------------------
# Single-purpose link tokens (trainee self-report, employer verification)
# ---------------------------------------------------------------------
# Signed with the same secret but carrying a "purpose" claim and NO role,
# so get_current_user() rejects them: a link token can never be used to
# call the admin/analyst API, and a login token can never be used as a
# link token.

PURPOSE_SELF_REPORT = "self_report"
PURPOSE_EMPLOYER_VERIFY = "employer_verify"


def create_link_token(purpose: str, subject: str, valid_days: int = 30) -> str:
    now = datetime.now(timezone.utc)
    payload = {"purpose": purpose, "sub": subject, "iat": now, "exp": now + timedelta(days=valid_days)}
    return jwt.encode(payload, _secret_key(), algorithm=JWT_ALGORITHM)


def read_link_token(token: str, purpose: str) -> str:
    """Return the token's subject, or raise 404 for any invalid/expired/mismatched token."""
    try:
        payload = jwt.decode(
            token,
            _secret_key(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub", "purpose"]},
        )
    except jwt.PyJWTError:
        payload = None
    if not payload or payload.get("purpose") != purpose or "role" in payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This link is invalid or has expired.",
        )
    return payload["sub"]
