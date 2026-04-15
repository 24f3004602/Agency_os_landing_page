import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_employee, require_owner
from app.database import get_db
from app.modules.m1_workforce.models_task import Task, TaskStatusHistory
from app.modules.people_and_tenant.users.models import Employee, User, UserRole
from app.modules.people_and_tenant.users.models import Client
from app.modules.m1_workforce.schemas_task import (
    TaskCreate,
    TaskHistoryEntry,
    TaskResponse,
    TaskStatusUpdate,
    TaskSummary,
    TaskUpdate,
    TaskVerify,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ── Helpers ─────────────────────────────────────────────────────────────────────

async def _get_employee_by_user(user: User, db: AsyncSession) -> Employee:
    result = await db.execute(
        select(Employee).where(Employee.user_id == user.id)
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee profile not found")
    return emp


async def _enrich_task(task: Task, db: AsyncSession) -> TaskResponse:
    """Adds employee name and client name to a task before returning."""
    assigned_to_name = None
    client_name = None

    # Get employee name
    emp_result = await db.execute(
        select(Employee).where(Employee.id == task.assigned_to)
    )
    emp = emp_result.scalar_one_or_none()
    if emp:
        user_result = await db.execute(
            select(User).where(User.id == emp.user_id)
        )
        user = user_result.scalar_one_or_none()
        assigned_to_name = user.full_name if user else None

    # Get client name
    if task.client_id:
        client_result = await db.execute(
            select(Client).where(Client.id == task.client_id)
        )
        client = client_result.scalar_one_or_none()
        client_name = client.company_name if client else None

    history = [
        TaskHistoryEntry.model_validate(h) for h in task.history
    ]

    return TaskResponse(
        id=task.id,
        agency_id=task.agency_id,
        assigned_to=task.assigned_to,
        assigned_to_name=assigned_to_name,
        assigned_by=task.assigned_by,
        client_id=task.client_id,
        client_name=client_name,
        title=task.title,
        description=task.description,
        priority=task.priority,
        status=task.status,
        deadline=task.deadline,
        rejection_comment=task.rejection_comment,
        history=history,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _write_history(
    task: Task,
    to_status: str,
    changed_by: uuid.UUID | None,
    comment: str | None = None,
) -> TaskStatusHistory:
    return TaskStatusHistory(
        task_id=task.id,
        changed_by=changed_by,
        from_status=task.status,
        to_status=to_status,
        comment=comment,
        changed_at=datetime.now(timezone.utc),
    )


# ── Owner: Create task ───────────────────────────────────────────────────────────

@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    body: TaskCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> TaskResponse:
    # Verify the assigned employee belongs to this agency
    emp_result = await db.execute(
        select(Employee).where(
            Employee.id == body.assigned_to,
            Employee.agency_id == current_user.agency_id,
        )
    )
    if not emp_result.scalar_one_or_none():
        raise HTTPException(404, "Employee not found in your agency")

    task = Task(
        agency_id=current_user.agency_id,
        assigned_to=body.assigned_to,
        assigned_by=current_user.id,
        client_id=body.client_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        deadline=body.deadline,
        status="created",
    )
    db.add(task)
    await db.flush()  # get task.id before writing history

    history_entry = _write_history(task, "created", current_user.id)
    db.add(history_entry)

    await db.commit()
    await db.refresh(task, ["history"])
    return await _enrich_task(task, db)


# ── Owner: List all tasks ────────────────────────────────────────────────────────

@router.get("", response_model=list[TaskSummary])
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
    employee_id: uuid.UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    priority: str | None = Query(None),
) -> list[TaskSummary]:
    query = select(Task).where(Task.agency_id == current_user.agency_id)

    if employee_id:
        query = query.where(Task.assigned_to == employee_id)
    if status_filter:
        query = query.where(Task.status == status_filter)
    if priority:
        query = query.where(Task.priority == priority)

    query = query.order_by(Task.created_at.desc())
    result = await db.execute(query)
    tasks = result.scalars().all()

    summaries = []
    for t in tasks:
        # Get employee name
        assigned_to_name = None
        emp_res = await db.execute(select(Employee).where(Employee.id == t.assigned_to))
        emp = emp_res.scalar_one_or_none()
        if emp:
            u_res = await db.execute(select(User).where(User.id == emp.user_id))
            u = u_res.scalar_one_or_none()
            assigned_to_name = u.full_name if u else None

        # Get client name
        client_name = None
        if t.client_id:
            c_res = await db.execute(select(Client).where(Client.id == t.client_id))
            c = c_res.scalar_one_or_none()
            client_name = c.company_name if c else None

        summaries.append(TaskSummary(
            id=t.id,
            title=t.title,
            priority=t.priority,
            status=t.status,
            deadline=t.deadline,
            assigned_to_name=assigned_to_name,
            client_name=client_name,
            created_at=t.created_at,
        ))

    return summaries


# ── Employee: their own tasks ────────────────────────────────────────────────────

@router.get("/my", response_model=list[TaskSummary])
async def my_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
    status_filter: str | None = Query(None, alias="status"),
) -> list[TaskSummary]:
    employee = await _get_employee_by_user(current_user, db)

    query = select(Task).where(Task.assigned_to == employee.id)
    if status_filter:
        query = query.where(Task.status == status_filter)
    query = query.order_by(Task.deadline.asc().nulls_last(), Task.created_at.desc())

    result = await db.execute(query)
    tasks = result.scalars().all()

    return [
        TaskSummary(
            id=t.id,
            title=t.title,
            priority=t.priority,
            status=t.status,
            deadline=t.deadline,
            created_at=t.created_at,
        )
        for t in tasks
    ]


# ── Both: Get single task ────────────────────────────────────────────────────────

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.agency_id == current_user.agency_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    # Employees can only see their own tasks
    if current_user.role == UserRole.EMPLOYEE:
        employee = await _get_employee_by_user(current_user, db)
        if task.assigned_to != employee.id:
            raise HTTPException(403, "You can only view your own tasks")

    await db.refresh(task, ["history"])
    return await _enrich_task(task, db)


# ── Employee: update status ──────────────────────────────────────────────────────

@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: uuid.UUID,
    body: TaskStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
) -> TaskResponse:
    employee = await _get_employee_by_user(current_user, db)

    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.assigned_to == employee.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found or not assigned to you")

    # Enforce valid transitions
    valid_transitions = {
        "created":     ["in_progress"],
        "in_progress": ["submitted"],
        "rejected":    ["in_progress"],
        "overdue":     ["in_progress"],
    }
    allowed = valid_transitions.get(task.status, [])
    if body.status not in allowed:
        raise HTTPException(
            400,
            f"Cannot move task from '{task.status}' to '{body.status}'. "
            f"Allowed: {allowed or 'none'}",
        )

    history_entry = _write_history(task, body.status, current_user.id)
    task.status = body.status
    db.add(history_entry)

    await db.commit()
    await db.refresh(task, ["history"])
    return await _enrich_task(task, db)


# ── Owner: verify or reject ──────────────────────────────────────────────────────

@router.patch("/{task_id}/verify", response_model=TaskResponse)
async def verify_task(
    task_id: uuid.UUID,
    body: TaskVerify,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.agency_id == current_user.agency_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status != "submitted":
        raise HTTPException(
            400,
            f"Task must be in 'submitted' status to verify/reject. Current: '{task.status}'",
        )

    if body.action == "rejected" and not body.comment:
        raise HTTPException(400, "A comment is required when rejecting a task")

    history_entry = _write_history(
        task, body.action, current_user.id, comment=body.comment
    )

    task.status = body.action
    if body.action == "rejected":
        task.rejection_comment = body.comment
    else:
        task.rejection_comment = None  # clear on verify

    db.add(history_entry)
    await db.commit()
    await db.refresh(task, ["history"])
    return await _enrich_task(task, db)


# ── Owner: update task metadata ──────────────────────────────────────────────────

@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> TaskResponse:
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.agency_id == current_user.agency_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task, ["history"])
    return await _enrich_task(task, db)


# ── Owner: delete task ───────────────────────────────────────────────────────────

@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> None:
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.agency_id == current_user.agency_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    await db.delete(task)
    await db.commit()