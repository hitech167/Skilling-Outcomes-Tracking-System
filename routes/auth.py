"""
Authentication routes.

POST /api/auth/token   -> exchange username/password for a JWT (OAuth2 password form,
                          so Swagger's "Authorize" button works)
GET  /api/auth/me      -> who am I / which role
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from schemas.auth import CurrentUserResponse, TokenResponse
from services.auth import authenticate, create_access_token, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/token", response_model=TokenResponse, summary="Log in and get an access token")
def login(form: OAuth2PasswordRequestForm = Depends()):
    role = authenticate(form.username, form.password)
    if role is None:
        # Never log the submitted password.
        logger.info("Failed login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(form.username.strip(), role)
    return TokenResponse(access_token=token, role=role, expires_in=expires_in)


@router.get("/me", response_model=CurrentUserResponse, summary="Current user and role")
def me(user: dict = Depends(get_current_user)):
    return CurrentUserResponse(**user)
