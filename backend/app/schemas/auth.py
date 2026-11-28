"""Pydantic schemas for authentication requests and responses."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    """Credentials submitted by a user during login."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Remove surrounding whitespace and normalize email casing."""
        return value.strip().lower()


class TokenResponse(BaseModel):
    """JWT access token returned after successful authentication."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"


class UserResponse(BaseModel):
    """Public user information; never expose password hashes."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str
