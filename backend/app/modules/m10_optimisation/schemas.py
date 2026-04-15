import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


# ── Config ───────────────────────────────────────────────────────────────────

class OptimisationConfigCreate(BaseModel):
    mode: Literal["advisory", "autonomous"] = "advisory"
    max_budget_change_pct: float = Field(default=20.0, ge=1, le=50)
    max_bid_change_pct: float = Field(default=15.0, ge=1, le=40)
    min_daily_budget: Decimal = Field(default=Decimal("500"), ge=0)
    approved_change_types: list[str] = Field(
        default=["pause_ad"],
        description="Valid: pause_ad, pause_adset, adjust_bid, reallocate_budget, scale_budget",
    )
    target_roas: float | None = None
    target_ctr: float | None = None
    target_cpc: float | None = None


class OptimisationConfigResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    mode: str
    max_budget_change_pct: float
    max_bid_change_pct: float
    min_daily_budget: Decimal
    approved_change_types: list[str]
    autonomous_enabled: bool
    target_roas: float | None
    target_ctr: float | None
    target_cpc: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Recommendation ───────────────────────────────────────────────────────────

class RecommendationResponse(BaseModel):
    id: uuid.UUID
    change_type: str
    platform: str
    entity_id: str | None
    entity_name: str | None
    description: str
    current_value: str | None
    proposed_value: str | None
    confidence_score: float
    rationale: str | None
    status: str
    executed_at: datetime | None
    execution_result: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Run ──────────────────────────────────────────────────────────────────────

class TriggerRunRequest(BaseModel):
    client_id: uuid.UUID


class ApproveRecommendationsRequest(BaseModel):
    recommendation_ids: list[uuid.UUID]


class OptimisationRunResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    status: str
    mode: str
    analysis_summary: str | None
    total_recommendations: int
    approved_count: int
    executed_count: int
    error_message: str | None
    recommendations: list[RecommendationResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class OptimisationRunSummary(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    status: str
    mode: str
    total_recommendations: int
    executed_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Predictive alerts ────────────────────────────────────────────────────────

class PredictiveAlertResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    severity: str
    status: str
    kpi_name: str
    current_value: float | None
    target_value: float | None
    projected_eom_value: float | None
    gap_percentage: float | None
    suggested_action: str | None
    days_remaining: int | None
    acknowledged_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}