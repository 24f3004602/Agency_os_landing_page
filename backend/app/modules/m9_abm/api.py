import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_module, require_owner
from app.database import get_db
from app.modules.m9_abm.models import AbmAccount, AbmAccountNote, AbmTouch, ABM_STAGES
from app.modules.people_and_tenant.users.models import Employee, User
from app.modules.m9_abm.schemas import (
    AbmAccountCreate,
    AbmAccountResponse,
    AbmAccountSummary,
    AbmNoteCreate,
    AbmNoteResponse,
    AbmStageUpdate,
    AbmTouchCreate,
    AbmTouchResponse,
)

router = APIRouter(prefix="/m9", tags=["M9 - ABM Orchestrator"])

M9 = Depends(require_module("M9"))


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_assigned_name(
    assigned_to: uuid.UUID | None,
    db: AsyncSession,
) -> str | None:
    if not assigned_to:
        return None
    emp_result = await db.execute(
        select(Employee).where(Employee.id == assigned_to)
    )
    emp = emp_result.scalar_one_or_none()
    if not emp:
        return None
    user_result = await db.execute(
        select(User).where(User.id == emp.user_id)
    )
    user = user_result.scalar_one_or_none()
    return user.full_name if user else None


async def _build_account_response(
    account: AbmAccount,
    db: AsyncSession,
    include_touches: bool = True,
    include_notes: bool = True,
) -> AbmAccountResponse:
    assigned_name = await _get_assigned_name(account.assigned_to, db)

    # Days since last touch
    now = datetime.now(timezone.utc)
    days_since = None
    if account.last_touch_at:
        days_since = (now - account.last_touch_at).days

    # Total touches
    touches_result = await db.execute(
        select(AbmTouch).where(AbmTouch.account_id == account.id)
    )
    all_touches = touches_result.scalars().all()
    total_touches = len(all_touches)

    # Recent 5 touches
    recent_touches = []
    if include_touches:
        sorted_touches = sorted(
            all_touches,
            key=lambda t: t.touched_at,
            reverse=True,
        )[:5]
        recent_touches = [
            AbmTouchResponse.model_validate(t) for t in sorted_touches
        ]

    # Notes
    notes = []
    if include_notes:
        notes_result = await db.execute(
            select(AbmAccountNote).where(
                AbmAccountNote.account_id == account.id
            ).order_by(AbmAccountNote.created_at.desc())
        )
        notes = [
            AbmNoteResponse.model_validate(n)
            for n in notes_result.scalars().all()
        ]

    return AbmAccountResponse(
        id=account.id,
        agency_id=account.agency_id,
        lead_id=account.lead_id,
        company_name=account.company_name,
        website=account.website,
        industry=account.industry,
        company_size=account.company_size,
        contact_name=account.contact_name,
        contact_email=account.contact_email,
        contact_linkedin=account.contact_linkedin,
        contact_phone=account.contact_phone,
        stage=account.stage,
        assigned_to=account.assigned_to,
        assigned_to_name=assigned_name,
        intelligence_summary=account.intelligence_summary,
        ai_next_action=account.ai_next_action,
        last_touch_at=account.last_touch_at,
        stage_entered_at=account.stage_entered_at,
        days_since_last_touch=days_since,
        total_touches=total_touches,
        recent_touches=recent_touches,
        notes=notes,
        created_at=account.created_at,
    )


# ── Create account ────────────────────────────────────────────────────────────

@router.post("/accounts", response_model=AbmAccountResponse, status_code=201)
async def create_abm_account(
    body: AbmAccountCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M9],
) -> AbmAccountResponse:
    """
    Adds a target account to the ABM pipeline.
    Starts at 'identified' stage.
    """
    if body.assigned_to:
        emp_result = await db.execute(
            select(Employee).where(
                Employee.id == body.assigned_to,
                Employee.agency_id == current_user.agency_id,
            )
        )
        if not emp_result.scalar_one_or_none():
            raise HTTPException(404, "Employee not found in your agency")

    account = AbmAccount(
        agency_id=current_user.agency_id,
        lead_id=body.lead_id,
        company_name=body.company_name,
        website=body.website,
        industry=body.industry,
        company_size=body.company_size,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        contact_linkedin=body.contact_linkedin,
        contact_phone=body.contact_phone,
        assigned_to=body.assigned_to,
        stage="identified",
        stage_entered_at=datetime.now(timezone.utc),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return await _build_account_response(account, db)


# ── List accounts ─────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=list[AbmAccountSummary])
async def list_abm_accounts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M9],
    stage: str | None = Query(None),
    assigned_to: uuid.UUID | None = Query(None),
    stale_only: bool = Query(
        False,
        description="Only show accounts with no touch in 7+ days"
    ),
) -> list[AbmAccountSummary]:
    """
    Lists all ABM accounts sorted by days since last touch
    (most stale first — these need attention).
    """
    query = select(AbmAccount).where(
        AbmAccount.agency_id == current_user.agency_id
    )
    if stage:
        query = query.where(AbmAccount.stage == stage)
    if assigned_to:
        query = query.where(AbmAccount.assigned_to == assigned_to)

    result = await db.execute(query)
    accounts = result.scalars().all()

    now = datetime.now(timezone.utc)
    summaries = []

    for account in accounts:
        days_since = None
        if account.last_touch_at:
            days_since = (now - account.last_touch_at).days
        elif account.created_at:
            days_since = (now - account.created_at).days

        if stale_only and (days_since is None or days_since < 7):
            continue

        assigned_name = await _get_assigned_name(account.assigned_to, db)

        touches_result = await db.execute(
            select(AbmTouch).where(AbmTouch.account_id == account.id)
        )
        total_touches = len(touches_result.scalars().all())

        summaries.append(AbmAccountSummary(
            id=account.id,
            company_name=account.company_name,
            industry=account.industry,
            stage=account.stage,
            assigned_to_name=assigned_name,
            ai_next_action=account.ai_next_action,
            last_touch_at=account.last_touch_at,
            days_since_last_touch=days_since,
            total_touches=total_touches,
            created_at=account.created_at,
        ))

    # Sort by days stale descending
    summaries.sort(
        key=lambda x: x.days_since_last_touch or 999,
        reverse=True,
    )

    return summaries


# ── Get single account ────────────────────────────────────────────────────────

@router.get("/accounts/{account_id}", response_model=AbmAccountResponse)
async def get_abm_account(
    account_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M9],
) -> AbmAccountResponse:
    result = await db.execute(
        select(AbmAccount).where(
            AbmAccount.id == account_id,
            AbmAccount.agency_id == current_user.agency_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    return await _build_account_response(account, db)


# ── Advance stage manually ────────────────────────────────────────────────────

@router.patch("/accounts/{account_id}/stage", response_model=AbmAccountResponse)
async def update_account_stage(
    account_id: uuid.UUID,
    body: AbmStageUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M9],
) -> AbmAccountResponse:
    """
    Owner or AE manually moves an account to a different stage.
    Optionally adds a note explaining the reason.
    Used for proposal and closing stages that require human judgement.
    """
    result = await db.execute(
        select(AbmAccount).where(
            AbmAccount.id == account_id,
            AbmAccount.agency_id == current_user.agency_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    if body.stage not in ABM_STAGES:
        raise HTTPException(400, f"Invalid stage: {body.stage}")

    old_stage = account.stage
    account.stage = body.stage
    account.stage_entered_at = datetime.now(timezone.utc)

    # Add note if reason provided
    if body.note:
        note = AbmAccountNote(
            account_id=account.id,
            agency_id=current_user.agency_id,
            written_by=current_user.id,
            content=f"Stage change: {old_stage} → {body.stage}\n{body.note}",
        )
        db.add(note)

    await db.commit()
    await db.refresh(account)
    return await _build_account_response(account, db)


# ── Trigger orchestration ─────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/orchestrate", status_code=202)
async def orchestrate_account(
    account_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M9],
) -> dict:
    """
    Triggers the ABM Orchestration Agent for this account.
    Agent evaluates state, recommends next touch, generates
    content, routes it, and advances stage if appropriate.

    Returns 202 — check GET /m9/accounts/{id} after ~20 seconds.
    """
    result = await db.execute(
        select(AbmAccount).where(
            AbmAccount.id == account_id,
            AbmAccount.agency_id == current_user.agency_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    if account.stage in ("closed_won", "closed_lost"):
        raise HTTPException(
            400,
            f"Cannot orchestrate a {account.stage} account",
        )

    account_id_str = str(account.id)
    agency_id_str = str(current_user.agency_id)

    async def _run():
        from app.modules.m9_abm.agent import run_abm_agent
        await run_abm_agent(
            account_id=account_id_str,
            agency_id=agency_id_str,
        )

    background_tasks.add_task(_run)

    return {
        "status": "orchestration_started",
        "account": account.company_name,
        "current_stage": account.stage,
        "message": (
            "Agent running in background. "
            "Check GET /m9/accounts/{id} in ~20 seconds "
            "to see new touch and any stage advancement."
        ),
    }


# ── Log manual touch ──────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/touches", response_model=AbmTouchResponse)
async def log_manual_touch(
    account_id: uuid.UUID,
    body: AbmTouchCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M9],
) -> AbmTouchResponse:
    """
    Owner/AE logs a manually executed touch.
    e.g. 'I called them today — outcome: meeting booked'
    """
    result = await db.execute(
        select(AbmAccount).where(
            AbmAccount.id == account_id,
            AbmAccount.agency_id == current_user.agency_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    now = datetime.now(timezone.utc)
    touch_time = body.touched_at or now

    touch = AbmTouch(
        account_id=account.id,
        agency_id=current_user.agency_id,
        channel=body.channel,
        direction=body.direction,
        touch_type=body.touch_type,
        subject=body.subject,
        content=body.content,
        ai_generated=False,
        outcome=body.outcome,
        touched_at=touch_time,
    )
    db.add(touch)

    # Update account last touch
    account.last_touch_at = touch_time

    # If inbound response logged → advance to engaged if in first_touch
    if (
        body.direction == "inbound"
        and account.stage == "first_touch"
        and body.outcome in ("replied", "meeting_booked", "proposal_requested")
    ):
        account.stage = "engaged"
        account.stage_entered_at = now

    await db.commit()
    await db.refresh(touch)
    return AbmTouchResponse.model_validate(touch)


# ── Add note ──────────────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/notes", response_model=AbmNoteResponse)
async def add_account_note(
    account_id: uuid.UUID,
    body: AbmNoteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M9],
) -> AbmNoteResponse:
    result = await db.execute(
        select(AbmAccount).where(
            AbmAccount.id == account_id,
            AbmAccount.agency_id == current_user.agency_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Account not found")

    note = AbmAccountNote(
        account_id=account_id,
        agency_id=current_user.agency_id,
        written_by=current_user.id,
        content=body.content,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return AbmNoteResponse.model_validate(note)


# ── Account feed ──────────────────────────────────────────────────────────────

@router.get("/feed", response_model=list[AbmAccountSummary])
async def get_abm_feed(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M9],
) -> list[AbmAccountSummary]:
    """
    The owner's ABM command centre feed.
    Returns all active accounts sorted by:
    1. Most stale (no touch in longest time) → need immediate attention
    2. Stage (proposal > engaged > first_touch > researching > identified)

    Closed accounts excluded.
    """
    result = await db.execute(
        select(AbmAccount).where(
            AbmAccount.agency_id == current_user.agency_id,
            AbmAccount.stage.notin_(["closed_won", "closed_lost"]),
        )
    )
    accounts = result.scalars().all()

    now = datetime.now(timezone.utc)

    stage_priority = {
        "proposal": 0,
        "engaged": 1,
        "first_touch": 2,
        "researching": 3,
        "identified": 4,
    }

    summaries = []
    for account in accounts:
        days_since = None
        if account.last_touch_at:
            days_since = (now - account.last_touch_at).days
        elif account.created_at:
            days_since = (now - account.created_at).days

        assigned_name = await _get_assigned_name(account.assigned_to, db)

        touches_result = await db.execute(
            select(AbmTouch).where(AbmTouch.account_id == account.id)
        )
        total_touches = len(touches_result.scalars().all())

        summaries.append(AbmAccountSummary(
            id=account.id,
            company_name=account.company_name,
            industry=account.industry,
            stage=account.stage,
            assigned_to_name=assigned_name,
            ai_next_action=account.ai_next_action,
            last_touch_at=account.last_touch_at,
            days_since_last_touch=days_since,
            total_touches=total_touches,
            created_at=account.created_at,
        ))

    # Sort: stage priority first, then days stale descending
    summaries.sort(
        key=lambda x: (
            stage_priority.get(x.stage, 99),
            -(x.days_since_last_touch or 0),
        )
    )

    return summaries