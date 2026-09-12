"""Request/response shapes for `/team/*` (spec §API), field names pinned by
`openapi.yaml`'s schemas — do not rename without updating the contract.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TeamConceptSummary(BaseModel):
    concept_id: str
    mean_mastery: float
    share_mastered: float
    at_risk_count: int


class RetentionBand(BaseModel):
    accuracy: float | None
    samples: int


class RetentionBands(BaseModel):
    d1: RetentionBand
    d7: RetentionBand
    d30: RetentionBand


class TeamPersonSummary(BaseModel):
    person_id: str
    adherence: float
    velocity: int
    last_active: datetime | None
    bypass_rate: float | None


class TeamOverviewResponse(BaseModel):
    concepts: list[TeamConceptSummary]
    people: list[TeamPersonSummary]
    # Subtree-pooled retention (concept-level aggregate, no per-item/per-
    # person detail) so the dashboard has a real curve even when an
    # individual's own band is too thin to report.
    retention: RetentionBands


class TeamConceptPersonState(BaseModel):
    person_id: str
    p_known: float
    mastered: bool


class TeamConceptDetailResponse(BaseModel):
    concept_id: str
    people: list[TeamConceptPersonState]


class ProgressEntry(BaseModel):
    concept_id: str
    p_known: float
    mastered: bool
    due_count: int
    unlocked: bool


class TeamPersonDetailResponse(BaseModel):
    person_id: str
    concepts: list[ProgressEntry]
    adherence: float
    velocity: int
    due_count: int
    last_active: datetime | None
    bypass_rate: float | None
    retention: RetentionBands
    calibration: float | None


class Recommendation(BaseModel):
    concept_id: str
    score: float
    mean_mastery: float
    dependents_count: int


class RecommendationsResponse(BaseModel):
    recommendations: list[Recommendation] = Field(max_length=5)


class TeamDigestAtRisk(BaseModel):
    person_id: str
    concept_id: str


class TeamDigestResponse(BaseModel):
    subtree_root_id: str
    period_start: datetime
    period_end: datetime
    concepts: list[TeamConceptSummary]
    at_risk: list[TeamDigestAtRisk]
    recommendations: list[Recommendation]


class FocusCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_kind: str
    scope_person_id: str
    concept_id: str
    weight: float = Field(default=1.5, gt=0)
    expires_at: datetime | None = None


class FocusOut(BaseModel):
    id: str
    scope_kind: str
    scope_person_id: str
    concept_id: str
    set_by: str
    weight: float
    expires_at: datetime | None
    created_at: datetime


class AuditEntryOut(BaseModel):
    id: str
    actor_person_id: str
    subject_scope: str
    endpoint: str
    at: datetime


class AuditResponse(BaseModel):
    entries: list[AuditEntryOut]
