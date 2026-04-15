import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


# ── Onboarding ───────────────────────────────────────────────────────────────

class TriggerOnboardingRequest(BaseModel):
    client_id: uuid.UUID
    deal_notes: str | None = None


class OnboardingStepResponse(BaseModel):
    id: uuid.UUID
    step_name: str
    status: str
    output: str | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OnboardingFlowResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    status: str
    client_brief: str | None
    last_completed_node: str | None
    error_message: str | None
    steps: list[OnboardingStepResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Invoice ──────────────────────────────────────────────────────────────────

class LineItem(BaseModel):
    description: str = Field(..., min_length=1)
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal = Field(..., ge=0)


class InvoiceCreate(BaseModel):
    client_id: uuid.UUID
    line_items: list[LineItem] = Field(..., min_length=1)
    tax_percent: Decimal = Field(default=Decimal("18"), ge=0, le=100)
    due_date: datetime | None = None
    notes: str | None = None
    send_immediately: bool = True   # email to client on creation


class InvoiceStatusUpdate(BaseModel):
    status: Literal["paid", "overdue", "sent"]


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    invoice_number: str
    status: str
    line_items: list[dict]
    subtotal: Decimal
    tax_percent: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    due_date: datetime | None
    paid_at: datetime | None
    notes: str | None
    has_pdf: bool
    created_at: datetime

    model_config = {"from_attributes": True}