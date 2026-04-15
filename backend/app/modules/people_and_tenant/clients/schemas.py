import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# Create 
class ClientCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    contact_name: str = Field(..., min_length=1, max_length=255)
    contact_email: EmailStr
    contact_phone: str | None = None
    account_manager_id: uuid.UUID | None = None   # employee.id
    hubspot_deal_id: str | None = None
    notes: str | None = None


# ── Update ───────────────────────────────────────────────────────────────────

class ClientUpdate(BaseModel):
    company_name: str | None = Field(None, min_length=1, max_length=255)
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    status: str | None = None   # active | at_risk | paused | churned
    account_manager_id: uuid.UUID | None = None
    notes: str | None = None


# ── Response ─────────────────────────────────────────────────────────────────

class ClientResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    company_name: str
    contact_name: str
    contact_email: str
    contact_phone: str | None
    status: str
    account_manager_id: uuid.UUID | None
    account_manager_name: str | None = None   # joined
    hubspot_deal_id: str | None
    notes: str | None
    has_portal_access: bool = False           # True if user_id is set
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}