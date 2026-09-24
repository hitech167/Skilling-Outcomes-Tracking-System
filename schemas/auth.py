"""Pydantic schemas for authentication responses."""

from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_in: int


class CurrentUserResponse(BaseModel):
    username: str
    role: str
