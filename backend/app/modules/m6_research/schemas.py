import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Competitor schemas ───────────────────────────────────────────────────────

class TrackedCompetitorCreate(BaseModel):
    client_id: uuid.UUID
    competitor_name: str = Field(..., min_length=1, max_length=255)
    domain: str | None = None
    meta_page_id: str | None = None
    industry: str | None = None


class TrackedCompetitorResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    competitor_name: str
    domain: str | None
    meta_page_id: str | None
    industry: str | None
    is_active: bool
    brief_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Research run ─────────────────────────────────────────────────────────────

class ResearchRunRequest(BaseModel):
    client_id: uuid.UUID
    competitor_ids: list[uuid.UUID] | None = None
    # None = run for all tracked competitors of this client


# ── Brief schemas ────────────────────────────────────────────────────────────

class ResearchBriefSummary(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    competitor_name: str
    key_findings: list[str]
    acted_on: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ResearchBriefResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    competitor_id: uuid.UUID
    competitor_name: str
    brief_text: str | None
    key_findings: list[str]
    meta_ad_count: int | None = None
    has_serp_data: bool = False
    qdrant_point_id: str | None
    acted_on: bool
    created_at: datetime

    model_config = {"from_attributes": True}