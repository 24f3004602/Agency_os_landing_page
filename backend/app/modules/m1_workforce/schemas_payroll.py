import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ── Trigger a payroll run ────────────────────────────────────────────────────

class PayrollRunCreate(BaseModel):
    period_month: int = Field(..., ge=1, le=12)
    period_year: int = Field(..., ge=2020)
    notes: str | None = None


# ── Individual payslip in response ──────────────────────────────────────────

class PayslipResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    designation: str | None
    period_month: int
    period_year: int
    days_present: int
    hours_worked: Decimal
    gross_pay: Decimal
    deductions: Decimal
    allowances: Decimal
    net_pay: Decimal
    has_pdf: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Full payroll run with all payslips ───────────────────────────────────────

class PayrollRunResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    period_month: int
    period_year: int
    status: str
    total_gross: Decimal
    total_net: Decimal
    total_employees: int
    notes: str | None
    approved_at: datetime | None
    created_at: datetime
    payslips: list[PayslipResponse] = []

    model_config = {"from_attributes": True}


# ── Summary for list view ────────────────────────────────────────────────────

class PayrollRunSummary(BaseModel):
    id: uuid.UUID
    period_month: int
    period_year: int
    status: str
    total_net: Decimal
    total_employees: int
    created_at: datetime

    model_config = {"from_attributes": True}