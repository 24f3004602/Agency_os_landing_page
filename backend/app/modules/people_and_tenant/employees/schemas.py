import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, EmailStr, Field


CompensationType = Literal["fixed", "hourly"]


# Create

class EmployeeCreate(BaseModel):
    # User account fields
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)

    # Employee profile fields
    designation: str | None = None
    compensation_type: CompensationType = "fixed"
    compensation_rate: Decimal = Field(default=Decimal("0"), ge=0)


# Update

class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    designation: str | None = None
    compensation_type: CompensationType | None = None
    compensation_rate: Decimal | None = Field(None, ge=0)
    is_active: bool | None = None


# Response

class EmployeeResponse(BaseModel):
    # Employee profile
    id: uuid.UUID              # employee.id (used in task assignment etc)
    user_id: uuid.UUID
    agency_id: uuid.UUID
    designation: str | None
    compensation_type: str
    compensation_rate: Decimal
    is_active: bool
    created_at: datetime

    # From joined User row
    full_name: str
    email: str
    last_login: datetime | None

    model_config = {"from_attributes": True}