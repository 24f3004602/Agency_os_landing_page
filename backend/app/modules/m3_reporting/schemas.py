import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Config ───────────────────────────────────────────────────────────────────

class ReportConfigCreate(BaseModel):
    schedule: Literal["weekly", "monthly"] = "monthly"
    platforms: list[str] = Field(
        default=["ga4", "meta", "google_ads"],
        description="List of platforms: ga4, meta, google_ads",
    )
    ga4_property_id: str | None = None
    meta_ad_account_id: str | None = None
    google_ads_customer_id: str | None = None
    kpi_targets: dict | None = None   # e.g. {"roas": 3.0, "ctr": 2.5}


class ReportConfigResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    schedule: str
    platforms: list[str]
    ga4_property_id: str | None
    meta_ad_account_id: str | None
    google_ads_customer_id: str | None
    kpi_targets: dict | None
    last_report_sent_at: datetime | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Generate ─────────────────────────────────────────────────────────────────

class GenerateReportRequest(BaseModel):
    client_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    # Override config platforms for this run (optional)
    platforms: list[str] | None = None


# ── Report response ──────────────────────────────────────────────────────────

class ReportResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    period_start: datetime
    period_end: datetime
    period_label: str
    status: str
    narrative: str | None
    processed_metrics: dict | None
    has_pdf: bool
    delivered_at: datetime | None
    delivered_via: str | None
    client_replied: bool
    follow_up_sent: bool
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── List summary ─────────────────────────────────────────────────────────────

class ReportSummary(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    period_start: datetime
    period_end: datetime
    status: str
    has_pdf: bool
    delivered_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}