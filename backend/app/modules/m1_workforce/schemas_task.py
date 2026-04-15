import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Valid values ────────────────────────────────────────────────────────────────
TaskPriority = Literal["low", "medium", "high", "urgent"]
TaskStatus   = Literal["created", "in_progress", "submitted",
                        "verified", "rejected", "overdue"]


# ── Owner creates a task ────────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    priority: TaskPriority = "medium"
    deadline: datetime | None = None
    assigned_to: uuid.UUID          # employee id
    client_id: uuid.UUID | None = None


# ── Owner updates task metadata ─────────────────────────────────────────────────
class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    priority: TaskPriority | None = None
    deadline: datetime | None = None
    client_id: uuid.UUID | None = None


# ── Employee moves task forward ─────────────────────────────────────────────────
class TaskStatusUpdate(BaseModel):
    # Employee can only set these two
    status: Literal["in_progress", "submitted"]


# ── Owner verifies or rejects ───────────────────────────────────────────────────
class TaskVerify(BaseModel):
    action: Literal["verified", "rejected"]
    comment: str | None = None   # required when rejecting — enforced in endpoint


# ── History entry in response ───────────────────────────────────────────────────
class TaskHistoryEntry(BaseModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    comment: str | None
    changed_at: datetime
    changed_by: uuid.UUID | None

    model_config = {"from_attributes": True}


# ── Full task response ──────────────────────────────────────────────────────────
class TaskResponse(BaseModel):
    id: uuid.UUID
    agency_id: uuid.UUID
    assigned_to: uuid.UUID
    assigned_to_name: str | None = None   # joined — employee's full name
    assigned_by: uuid.UUID | None
    client_id: uuid.UUID | None
    client_name: str | None = None        # joined — client company name
    title: str
    description: str | None
    priority: str
    status: str
    deadline: datetime | None
    rejection_comment: str | None
    history: list[TaskHistoryEntry] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Minimal response for list views ────────────────────────────────────────────
class TaskSummary(BaseModel):
    id: uuid.UUID
    title: str
    priority: str
    status: str
    deadline: datetime | None
    assigned_to_name: str | None = None
    client_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}