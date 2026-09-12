"""Request/response shapes for `POST /admin/roster/import` (spec §API)."""

from __future__ import annotations

from pydantic import BaseModel

from learning_service.identity.schemas import PersonSummary

ROLES = {"tech_lead", "senior_swe", "junior_swe", "pm", "uxd"}


class RosterImportPerson(BaseModel):
    email: str
    display_name: str
    manager_email: str | None = None
    slack_user_id: str | None = None
    # Not provided leaves an existing person's is_operator/role untouched on
    # a reimport, same as manager_email/slack_user_id already do
    # (OPEN-QUESTIONS.md Q4).
    is_operator: bool | None = None
    role: str | None = None


class RosterImportRequest(BaseModel):
    persons: list[RosterImportPerson]


class RosterImportResult(BaseModel):
    created: int
    updated: int
    persons: list[PersonSummary]
