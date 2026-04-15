import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_employee, require_module, require_owner
from app.core.buffer import schedule_post
from app.config import settings
from app.database import get_db
from app.modules.m5_campaigns.models import Campaign, CampaignTask
from app.modules.people_and_tenant.users.models import Client, Employee, User, UserRole
from app.modules.m5_campaigns.schemas import (
    CampaignCreate,
    CampaignResponse,
    CampaignSummary,
    CampaignTaskApprove,
    CampaignTaskCreate,
    CampaignTaskReject,
    CampaignTaskResponse,
    CampaignTaskStatusUpdate,
    CampaignTaskSummary,
    CampaignUpdate,
)

router = APIRouter(prefix="/m5", tags=["M5 - Campaign Task Manager"])

M5 = Depends(require_module("M5"))

# Valid employee-initiated status transitions
EMPLOYEE_TRANSITIONS = {
    "brief":       "in_progress",
    "in_progress": "draft",
    "draft":       "review",
    "review":      "draft",   # revert to draft if more work needed
}


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_employee_for_user(
    user: User,
    db: AsyncSession,
) -> Employee:
    result = await db.execute(
        select(Employee).where(Employee.user_id == user.id)
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee profile not found")
    return emp


async def _build_task_response(
    task: CampaignTask,
    db: AsyncSession,
) -> CampaignTaskResponse:
    # Campaign name + client info
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == task.campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    campaign_name = campaign.name if campaign else "Unknown"

    client_name = "Unknown"
    client_id = campaign.client_id if campaign else None
    if client_id:
        client_result = await db.execute(
            select(Client).where(Client.id == client_id)
        )
        client = client_result.scalar_one_or_none()
        client_name = client.company_name if client else "Unknown"

    # Assigned employee name
    assigned_to_name = None
    if task.assigned_to:
        emp_result = await db.execute(
            select(Employee).where(Employee.id == task.assigned_to)
        )
        emp = emp_result.scalar_one_or_none()
        if emp:
            user_result = await db.execute(
                select(User).where(User.id == emp.user_id)
            )
            u = user_result.scalar_one_or_none()
            assigned_to_name = u.full_name if u else None

    return CampaignTaskResponse(
        id=task.id,
        agency_id=task.agency_id,
        campaign_id=task.campaign_id,
        campaign_name=campaign_name,
        client_id=client_id or task.agency_id,
        client_name=client_name,
        assigned_to=task.assigned_to,
        assigned_to_name=assigned_to_name,
        title=task.title,
        description=task.description,
        content_type=task.content_type,
        status=task.status,
        draft_content=task.draft_content,
        feedback=task.feedback,
        scheduled_at=task.scheduled_at,
        buffer_post_id=task.buffer_post_id,
        went_live_at=task.went_live_at,
        deadline=task.deadline,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def _build_campaign_response(
    campaign: Campaign,
    db: AsyncSession,
) -> CampaignResponse:
    client_result = await db.execute(
        select(Client).where(Client.id == campaign.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"

    # Task count and status breakdown
    tasks_result = await db.execute(
        select(CampaignTask).where(
            CampaignTask.campaign_id == campaign.id
        )
    )
    tasks = tasks_result.scalars().all()

    tasks_by_status: dict[str, int] = {}
    for task in tasks:
        tasks_by_status[task.status] = tasks_by_status.get(task.status, 0) + 1

    return CampaignResponse(
        id=campaign.id,
        agency_id=campaign.agency_id,
        client_id=campaign.client_id,
        client_name=client_name,
        name=campaign.name,
        description=campaign.description,
        platform=campaign.platform,
        status=campaign.status,
        start_date=campaign.start_date,
        end_date=campaign.end_date,
        budget=campaign.budget,
        task_count=len(tasks),
        tasks_by_status=tasks_by_status,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


# ── Campaigns: Create ────────────────────────────────────────────────────────

@router.post("/campaigns", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M5],
) -> CampaignResponse:
    """Owner creates a new campaign for a client."""
    # Verify client belongs to agency
    client_result = await db.execute(
        select(Client).where(
            Client.id == body.client_id,
            Client.agency_id == current_user.agency_id,
        )
    )
    if not client_result.scalar_one_or_none():
        raise HTTPException(404, "Client not found in your agency")

    campaign = Campaign(
        agency_id=current_user.agency_id,
        client_id=body.client_id,
        name=body.name,
        description=body.description,
        platform=body.platform,
        start_date=body.start_date,
        end_date=body.end_date,
        budget=body.budget,
        status="active",
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return await _build_campaign_response(campaign, db)


# ── Campaigns: List ──────────────────────────────────────────────────────────

@router.get("/campaigns", response_model=list[CampaignSummary])
async def list_campaigns(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M5],
    client_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    platform: str | None = Query(None),
) -> list[CampaignSummary]:
    query = select(Campaign).where(
        Campaign.agency_id == current_user.agency_id
    )
    if client_id:
        query = query.where(Campaign.client_id == client_id)
    if status:
        query = query.where(Campaign.status == status)
    if platform:
        query = query.where(Campaign.platform == platform)
    query = query.order_by(Campaign.created_at.desc())

    result = await db.execute(query)
    campaigns = result.scalars().all()

    summaries = []
    for c in campaigns:
        client_result = await db.execute(
            select(Client).where(Client.id == c.client_id)
        )
        client = client_result.scalar_one_or_none()

        task_count_result = await db.execute(
            select(CampaignTask).where(CampaignTask.campaign_id == c.id)
        )
        task_count = len(task_count_result.scalars().all())

        summaries.append(CampaignSummary(
            id=c.id,
            client_id=c.client_id,
            client_name=client.company_name if client else "Unknown",
            name=c.name,
            platform=c.platform,
            status=c.status,
            task_count=task_count,
            created_at=c.created_at,
        ))

    return summaries


# ── Campaigns: Get one ───────────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M5],
) -> CampaignResponse:
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.agency_id == current_user.agency_id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    return await _build_campaign_response(campaign, db)


# ── Campaigns: Update ────────────────────────────────────────────────────────

@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M5],
) -> CampaignResponse:
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.agency_id == current_user.agency_id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(campaign, field, value)

    await db.commit()
    await db.refresh(campaign)
    return await _build_campaign_response(campaign, db)


# ── Campaign Tasks: Add task to campaign ─────────────────────────────────────

@router.post(
    "/campaigns/{campaign_id}/tasks",
    response_model=CampaignTaskResponse,
    status_code=201,
)
async def create_campaign_task(
    campaign_id: uuid.UUID,
    body: CampaignTaskCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M5],
) -> CampaignTaskResponse:
    """Owner adds a deliverable task to a campaign."""
    campaign_result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.agency_id == current_user.agency_id,
        )
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    # Validate employee belongs to agency
    if body.assigned_to:
        emp_result = await db.execute(
            select(Employee).where(
                Employee.id == body.assigned_to,
                Employee.agency_id == current_user.agency_id,
            )
        )
        if not emp_result.scalar_one_or_none():
            raise HTTPException(404, "Employee not found in your agency")

    task = CampaignTask(
        agency_id=current_user.agency_id,
        campaign_id=campaign_id,
        assigned_to=body.assigned_to,
        title=body.title,
        description=body.description,
        content_type=body.content_type,
        deadline=body.deadline,
        status="brief",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return await _build_task_response(task, db)


# ── Campaign Tasks: List tasks in campaign ───────────────────────────────────

@router.get(
    "/campaigns/{campaign_id}/tasks",
    response_model=list[CampaignTaskResponse],
)
async def list_campaign_tasks(
    campaign_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status: str | None = Query(None),
) -> list[CampaignTaskResponse]:
    # Verify campaign belongs to agency
    campaign_result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.agency_id == current_user.agency_id,
        )
    )
    if not campaign_result.scalar_one_or_none():
        raise HTTPException(404, "Campaign not found")

    query = select(CampaignTask).where(
        CampaignTask.campaign_id == campaign_id
    )

    # Employee sees only tasks assigned to them
    if current_user.role == UserRole.EMPLOYEE:
        emp = await _get_employee_for_user(current_user, db)
        query = query.where(CampaignTask.assigned_to == emp.id)

    if status:
        query = query.where(CampaignTask.status == status)

    query = query.order_by(CampaignTask.created_at.asc())

    result = await db.execute(query)
    tasks = result.scalars().all()
    return [await _build_task_response(t, db) for t in tasks]


# ── Campaign Tasks: Get single task ─────────────────────────────────────────

@router.get("/tasks/{task_id}", response_model=CampaignTaskResponse)
async def get_campaign_task(
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CampaignTaskResponse:
    result = await db.execute(
        select(CampaignTask).where(
            CampaignTask.id == task_id,
            CampaignTask.agency_id == current_user.agency_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    # Employee can only see their own tasks
    if current_user.role == UserRole.EMPLOYEE:
        emp = await _get_employee_for_user(current_user, db)
        if task.assigned_to != emp.id:
            raise HTTPException(403, "You can only view tasks assigned to you")

    return await _build_task_response(task, db)


# ── Campaign Tasks: Employee updates status ───────────────────────────────────

@router.patch("/tasks/{task_id}/status", response_model=CampaignTaskResponse)
async def update_task_status(
    task_id: uuid.UUID,
    body: CampaignTaskStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
) -> CampaignTaskResponse:
    """
    Employee moves their task through the pipeline.
    brief → in_progress → draft → review

    When moving to draft or review, draft_content must be provided.
    """
    emp = await _get_employee_for_user(current_user, db)

    result = await db.execute(
        select(CampaignTask).where(
            CampaignTask.id == task_id,
            CampaignTask.assigned_to == emp.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            404,
            "Task not found or not assigned to you"
        )

    # Validate transition
    allowed_next = EMPLOYEE_TRANSITIONS.get(task.status)
    if body.status != allowed_next:
        raise HTTPException(
            400,
            f"Cannot move task from '{task.status}' to '{body.status}'. "
            f"Next allowed status: '{allowed_next}'",
        )

    # Require draft content when submitting draft or review
    if body.status in ("draft", "review"):
        content = body.draft_content or task.draft_content
        if not content:
            raise HTTPException(
                400,
                f"draft_content is required when moving to '{body.status}'",
            )
        task.draft_content = content

    task.status = body.status
    task.feedback = None  # clear old feedback when employee moves forward

    await db.commit()
    await db.refresh(task)
    return await _build_task_response(task, db)


# ── Campaign Tasks: Owner approves ───────────────────────────────────────────

@router.post("/tasks/{task_id}/approve", response_model=CampaignTaskResponse)
async def approve_campaign_task(
    task_id: uuid.UUID,
    body: CampaignTaskApprove,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> CampaignTaskResponse:
    """
    Owner approves a task in 'review' status.
    Triggers Buffer scheduling if credentials configured.
    Task moves to 'scheduled'.
    """
    result = await db.execute(
        select(CampaignTask).where(
            CampaignTask.id == task_id,
            CampaignTask.agency_id == current_user.agency_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status != "review":
        raise HTTPException(
            400,
            f"Task must be in 'review' status to approve. "
            f"Current: '{task.status}'",
        )

    if not task.draft_content:
        raise HTTPException(
            400,
            "Task has no draft content to approve"
        )

    # Schedule via Buffer
    profile_id = (
        body.buffer_profile_id
        or settings.buffer_default_profile_id
        or "default_profile"
    )

    scheduled_at_str = None
    if body.scheduled_at:
        scheduled_at_str = body.scheduled_at.isoformat()

    try:
        buffer_result = await schedule_post(
            content=task.draft_content,
            profile_id=profile_id,
            scheduled_at=scheduled_at_str,
        )
        task.buffer_post_id = buffer_result.get("id")
        task.scheduled_at = body.scheduled_at or datetime.now(timezone.utc)

    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Buffer scheduling failed: %s", e)
        # Don't block approval if Buffer fails
        task.scheduled_at = body.scheduled_at or datetime.now(timezone.utc)

    task.status = "scheduled"
    task.feedback = None

    await db.commit()
    await db.refresh(task)
    return await _build_task_response(task, db)


# ── Campaign Tasks: Owner rejects / requests changes ─────────────────────────

@router.post("/tasks/{task_id}/reject", response_model=CampaignTaskResponse)
async def reject_campaign_task(
    task_id: uuid.UUID,
    body: CampaignTaskReject,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> CampaignTaskResponse:
    """
    Owner requests changes on a task in 'review' status.
    Task reverts to 'draft' with feedback visible to employee.
    """
    result = await db.execute(
        select(CampaignTask).where(
            CampaignTask.id == task_id,
            CampaignTask.agency_id == current_user.agency_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status != "review":
        raise HTTPException(
            400,
            f"Task must be in 'review' to request changes. "
            f"Current: '{task.status}'",
        )

    task.status = "draft"
    task.feedback = body.feedback

    await db.commit()
    await db.refresh(task)
    return await _build_task_response(task, db)


# ── Employee: My campaign tasks ───────────────────────────────────────────────

@router.get("/tasks/my", response_model=list[CampaignTaskSummary])
async def my_campaign_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
    status: str | None = Query(None),
) -> list[CampaignTaskSummary]:
    """
    Employee sees all campaign tasks assigned to them
    across all campaigns. Sorted by deadline ascending.
    """
    emp = await _get_employee_for_user(current_user, db)

    query = select(CampaignTask).where(
        CampaignTask.assigned_to == emp.id
    )
    if status:
        query = query.where(CampaignTask.status == status)
    query = query.order_by(
        CampaignTask.deadline.asc().nulls_last(),
        CampaignTask.created_at.desc(),
    )

    result = await db.execute(query)
    tasks = result.scalars().all()

    summaries = []
    for t in tasks:
        campaign_result = await db.execute(
            select(Campaign).where(Campaign.id == t.campaign_id)
        )
        campaign = campaign_result.scalar_one_or_none()
        campaign_name = campaign.name if campaign else "Unknown"

        summaries.append(CampaignTaskSummary(
            id=t.id,
            campaign_id=t.campaign_id,
            campaign_name=campaign_name,
            title=t.title,
            content_type=t.content_type,
            status=t.status,
            assigned_to_name=None,  # it's always them
            deadline=t.deadline,
            created_at=t.created_at,
        ))

    return summaries