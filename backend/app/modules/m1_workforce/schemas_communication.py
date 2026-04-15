import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# Send email
class SendEmailRequest(BaseModel):
    client_id: uuid.UUID
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)


# Send WhatsApp
class SendWhatsAppRequest(BaseModel):
    client_id: uuid.UUID
    message: str = Field(..., min_length=1, max_length=4096)


# Log entry response
class CommunicationLogResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    employee_id: uuid.UUID | None
    employee_name: str | None
    client_id: uuid.UUID
    client_name: str
    direction: str
    channel: str
    subject: str | None
    body: str
    status: str
    is_flagged: bool
    flag_reason: str | None
    flag_reviewed: bool
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# Flag review 
class FlagReviewRequest(BaseModel):
    notes: str | None = None  # optional owner note on resolution