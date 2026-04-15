import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Brief schemas ────────────────────────────────────────────────────────────

ContentPlatform = Literal[
    "instagram", "facebook", "google_ads",
    "email", "linkedin", "twitter", "youtube"
]
ContentType = Literal[
    "social_post", "ad_copy", "email",
    "video_script", "carousel", "story", "reel_script"
]
ToneOfVoice = Literal[
    "professional", "casual", "witty",
    "urgent", "inspirational", "educational"
]


class ContentBriefCreate(BaseModel):
    client_id: uuid.UUID
    campaign_id: uuid.UUID | None = None
    campaign_task_id: uuid.UUID | None = None
    title: str = Field(..., min_length=1, max_length=500)
    objective: str = Field(..., min_length=10)
    target_audience: str | None = None
    key_message: str | None = None
    tone_of_voice: ToneOfVoice | None = "professional"
    platform: ContentPlatform = "instagram"
    content_type: ContentType = "social_post"
    word_limit: int | None = Field(None, ge=10, le=5000)
    reference_urls: str | None = None
    additional_notes: str | None = None
    num_variations: int = Field(default=3, ge=1, le=5)


class ContentBriefResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    campaign_id: uuid.UUID | None
    title: str
    objective: str
    target_audience: str | None
    key_message: str | None
    tone_of_voice: str | None
    platform: str
    content_type: str
    word_limit: int | None
    num_variations: int
    status: str
    drafts: list["ContentDraftResponse"] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContentBriefSummary(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    title: str
    platform: str
    content_type: str
    status: str
    num_variations: int
    draft_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Draft schemas ────────────────────────────────────────────────────────────

class ContentDraftResponse(BaseModel):
    id: uuid.UUID
    brief_id: uuid.UUID
    variation_number: int
    angle: str | None
    headline: str | None
    body_copy: str
    cta: str | None
    hashtags: str | None
    status: str
    buffer_post_id: str | None
    published_at: datetime | None
    rejection_feedback: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Approval schemas ─────────────────────────────────────────────────────────

class SubmitForApprovalRequest(BaseModel):
    draft_id: uuid.UUID
    send_via: Literal["portal", "whatsapp", "both"] = "both"


class ApprovalActionRequest(BaseModel):
    feedback: str | None = None   # required if rejecting


class ApprovalRequestResponse(BaseModel):
    id: uuid.UUID
    draft_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    brief_title: str
    draft_angle: str | None
    draft_body_preview: str
    status: str
    sent_via: str
    responded_at: datetime | None
    response_channel: str | None
    client_feedback: str | None
    reminder_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Pipeline view ────────────────────────────────────────────────────────────

class ContentPipelineItem(BaseModel):
    brief_id: uuid.UUID
    title: str
    platform: str
    content_type: str
    status: str
    draft_count: int
    pending_approvals: int
    approved_count: int
    published_count: int
    created_at: datetime

    model_config = {"from_attributes": True}