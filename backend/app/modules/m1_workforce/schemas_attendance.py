import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator


# Geofence Schemas
class GeofenceZoneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_metres: int = Field(default=100, ge=10, le=5000)
    notes: str | None = None


class GeofenceZoneUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    radius_metres: int | None = Field(None, ge=10, le=5000)
    is_active: bool | None = None
    notes: str | None = None


class GeofenceZoneResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    name: str
    latitude: float
    longitude: float
    radius_metres: int
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Attendance Schemas

class ClockInRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class ClockInResponse(BaseModel):
    session_id: uuid.UUID
    status: str                  # "clocked_in"
    zone_name: str | None        # matched zone name, or None if no match
    clock_in_time: datetime
    distance_to_zone_metres: float | None
    message: str


class ClockOutResponse(BaseModel):
    session_id: uuid.UUID
    status: str                  # "clocked_out"
    clock_in_time: datetime
    clock_out_time: datetime
    hours_worked: Decimal
    message: str


class AttendanceSessionResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    zone_id: uuid.UUID | None
    zone_name: str | None        # joined from GeofenceZone
    clock_in_latitude: float
    clock_in_longitude: float
    clock_in_time: datetime
    clock_out_time: datetime | None
    hours_worked: Decimal | None
    status: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TodayStatusResponse(BaseModel):
    is_clocked_in: bool
    session: AttendanceSessionResponse | None
    message: str


# Owner view — team attendance

class EmployeeAttendanceSummary(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    sessions: list[AttendanceSessionResponse]
    total_hours_this_month: Decimal
