import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Sequence schemas ─────────────────────────────────────────────────────────

class CreateSequenceRequest(BaseModel):
    lead_id: uuid.UUID
    send_mode: Literal["auto", "manual"] = "manual"
    assigned_to: uuid.UUID | None = None   # employee id


class OutreachStepResponse(BaseModel):
    id: uuid.UUID
    step_number: int
    channel: str
    subject: str | None
    body: str
    send_after_days: int
    status: str
    scheduled_send_at: datetime | None
    sent_at: datetime | None
    approved_by_ae: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class OutreachSequenceResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str
    lead_company: str
    assigned_to: uuid.UUID | None
    assigned_to_name: str | None
    status: str
    total_steps: int
    current_step: int
    send_mode: str
    icp_score_at_creation: float | None
    competitor_context_used: str | None
    replied_at: datetime | None
    steps: list[OutreachStepResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class OutreachSequenceSummary(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str
    lead_company: str
    status: str
    total_steps: int
    current_step: int
    send_mode: str
    icp_score_at_creation: float | None
    replied_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Step approval ────────────────────────────────────────────────────────────

class ApproveStepRequest(BaseModel):
    step_id: uuid.UUID


# ── Reply webhook ─────────────────────────────────────────────────────────────

class ReplyWebhookPayload(BaseModel):
    gmail_message_id: str
    from_email: str
    subject: str | None = None
    body: str | None = None