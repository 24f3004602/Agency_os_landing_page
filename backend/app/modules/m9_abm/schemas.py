import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


# ── Account schemas ──────────────────────────────────────────────────────────

AbmStage = Literal[
    "identified", "researching", "first_touch",
    "engaged", "proposal", "closed_won", "closed_lost"
]


class AbmAccountCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    website: str | None = None
    industry: str | None = None
    company_size: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_linkedin: str | None = None
    contact_phone: str | None = None
    assigned_to: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None   # link to existing M7 lead


class AbmStageUpdate(BaseModel):
    stage: AbmStage
    note: str | None = None   # reason for stage change


# ── Touch schemas ────────────────────────────────────────────────────────────

class AbmTouchCreate(BaseModel):
    channel: Literal["email", "linkedin", "whatsapp", "call", "meeting", "ad", "other"]
    direction: Literal["outbound", "inbound"] = "outbound"
    touch_type: Literal[
        "first_contact", "follow_up", "content_share",
        "proposal", "breakup", "other"
    ] = "other"
    subject: str | None = None
    content: str | None = None
    outcome: str | None = None
    touched_at: datetime | None = None


class AbmTouchResponse(BaseModel):
    id: uuid.UUID
    channel: str
    direction: str
    touch_type: str
    subject: str | None
    content: str | None
    ai_generated: bool
    outcome: str | None
    touched_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Note schemas ─────────────────────────────────────────────────────────────

class AbmNoteCreate(BaseModel):
    content: str = Field(..., min_length=1)


class AbmNoteResponse(BaseModel):
    id: uuid.UUID
    content: str
    written_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Account response ─────────────────────────────────────────────────────────

class AbmAccountResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    lead_id: uuid.UUID | None
    company_name: str
    website: str | None
    industry: str | None
    company_size: str | None
    contact_name: str | None
    contact_email: str | None
    contact_linkedin: str | None
    contact_phone: str | None
    stage: str
    assigned_to: uuid.UUID | None
    assigned_to_name: str | None
    intelligence_summary: str | None
    ai_next_action: str | None
    last_touch_at: datetime | None
    stage_entered_at: datetime | None
    days_since_last_touch: int | None
    total_touches: int
    recent_touches: list[AbmTouchResponse] = []
    notes: list[AbmNoteResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class AbmAccountSummary(BaseModel):
    id: uuid.UUID
    company_name: str
    industry: str | None
    stage: str
    assigned_to_name: str | None
    ai_next_action: str | None
    last_touch_at: datetime | None
    days_since_last_touch: int | None
    total_touches: int
    created_at: datetime

    model_config = {"from_attributes": True}