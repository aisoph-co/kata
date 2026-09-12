"""Request/response shapes for the identity endpoints (spec §API)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IdentityResolveRequest(BaseModel):
    platform: str
    external_id: str
    alt_id: str | None = None


class PersonSummary(BaseModel):
    id: str
    display_name: str
    email: str
    is_operator: bool
    role: str | None = None


class LinkCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class IdentityLinkRequest(BaseModel):
    code: str
    platform: str
    external_id: str
    alt_id: str | None = None


class IdentityOut(BaseModel):
    id: str
    person_id: str
    platform: str
    external_id: str
    alt_id: str | None = None
    is_primary: bool
    linked_at: datetime
