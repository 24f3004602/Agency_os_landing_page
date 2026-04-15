import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class ChurnAlertResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    client_status: str
    risk_score: float
    trigger_reasons: list[str]
    retention_actions: list[str]
    competitor_context: str | None
    status: str
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClientRiskScore(BaseModel):
    client_id: uuid.UUID
    client_name: str
    client_status: str
    risk_score: float | None     # None if never scanned
    last_alert_at: datetime | None
    open_alerts: int

    model_config = {"from_attributes": True}


class ResolveAlertRequest(BaseModel):
    resolution: str = Field(
        ...,
        description="false_positive | resolved"
    )
    note: str | None = None