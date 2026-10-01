"""
app/schemas/auth.py

Pydantic v2 schemas for the authentication boundary.

LoginResponse intentionally omits the user's email and tenant name so a token
response carries only what a client needs to route on. UserResponse is the
authenticated-identity shape and exposes no password material.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    tenant_id: uuid.UUID


class UserResponse(BaseModel):
    """Authenticated identity. Never includes password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    tenant_id: uuid.UUID
    agency_id: uuid.UUID | None
