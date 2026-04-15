import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


# Task status literal
CampaignTaskStatus = Literal[
    "brief", "in_progress", "draft",
    "review", "approved", "scheduled", "live"
]

ContentType = Literal[
    "ad_copy", "social_post", "email",
    "blog", "video_script", "banner"
]

CampaignPlatform = Literal[
    "meta", "google_ads", "email",
    "social", "content", "multi_channel"
]


# Campaign schemas

class CampaignCreate(BaseModel):
    client_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    platform: CampaignPlatform = "social"
    start_date: datetime | None = None
    end_date: datetime | None = None
    budget: str | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    platform: CampaignPlatform | None = None
    status: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    budget: str | None = None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    name: str
    description: str | None
    platform: str
    status: str
    start_date: datetime | None
    end_date: datetime | None
    budget: str | None
    task_count: int = 0
    tasks_by_status: dict = {}
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignSummary(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    name: str
    platform: str
    status: str
    task_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# Campaign task schemas 

class CampaignTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    content_type: ContentType = "social_post"
    assigned_to: uuid.UUID | None = None    # employee id
    deadline: datetime | None = None


class CampaignTaskStatusUpdate(BaseModel):
    # Employee can move: brief→in_progress, in_progress→draft, draft→review
    status: Literal["in_progress", "draft", "review"]
    draft_content: str | None = None  # required when moving to draft or review


class CampaignTaskApprove(BaseModel):
    # Buffer profile to schedule to (optional — uses default if not provided)
    buffer_profile_id: str | None = None
    scheduled_at: datetime | None = None  # None = add to Buffer queue


class CampaignTaskReject(BaseModel):
    feedback: str = Field(..., min_length=1)  # required — tell employee what to fix


class CampaignTaskResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    campaign_id: uuid.UUID
    campaign_name: str
    client_id: uuid.UUID
    client_name: str
    assigned_to: uuid.UUID | None
    assigned_to_name: str | None
    title: str
    description: str | None
    content_type: str
    status: str
    draft_content: str | None
    feedback: str | None
    scheduled_at: datetime | None
    buffer_post_id: str | None
    went_live_at: datetime | None
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignTaskSummary(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    campaign_name: str
    title: str
    content_type: str
    status: str
    assigned_to_name: str | None
    deadline: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}