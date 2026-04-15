import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ── ICP ──────────────────────────────────────────────────────────────────────

class IcpProfileCreate(BaseModel):
    ideal_industries: str = Field(
        default="D2C brands, e-commerce, retail, food & beverage"
    )
    ideal_company_size: str = Field(
        default="10-500 employees, Series A to Series C"
    )
    ideal_ad_budget: str = Field(
        default="Monthly ad spend of ₹2L to ₹50L"
    )
    ideal_decision_maker: str = Field(
        default="Founder, CMO, Marketing Head, Growth Manager"
    )
    ideal_pain_points: str = Field(
        default="Struggling with ROAS, want to scale paid ads"
    )
    disqualifiers: str = Field(
        default="Budget under ₹1L/month, no product-market fit"
    )
    high_priority_threshold: int = Field(default=70, ge=0, le=100)


class IcpProfileResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    ideal_industries: str
    ideal_company_size: str
    ideal_ad_budget: str
    ideal_decision_maker: str
    ideal_pain_points: str
    disqualifiers: str
    high_priority_threshold: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Lead ─────────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str | None = None
    designation: str | None = None
    company_name: str = Field(..., min_length=1, max_length=255)
    company_size: str | None = None
    industry: str | None = None
    website: str | None = None
    monthly_ad_budget: str | None = None
    pain_points: str | None = None
    notes: str | None = None
    source: str = "manual"
    assigned_to: uuid.UUID | None = None   # employee id


class LeadStatusUpdate(BaseModel):
    status: Literal[
        "new", "scored", "contacted",
        "qualified", "disqualified", "converted"
    ]


class LeadScoreResponse(BaseModel):
    score: float
    rationale: str
    strengths: list[str]
    concerns: list[str]
    next_action: str
    hubspot_updated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    designation: str | None
    company_name: str
    company_size: str | None
    industry: str | None
    website: str | None
    monthly_ad_budget: str | None
    pain_points: str | None
    notes: str | None
    source: str
    status: str
    hubspot_deal_id: str | None
    assigned_to: uuid.UUID | None
    assigned_to_name: str | None
    score_data: LeadScoreResponse | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    company_name: str
    industry: str | None
    source: str
    status: str
    icp_score: float | None
    assigned_to_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}