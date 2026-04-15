import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_module, require_owner
from app.database import get_db
from app.modules.m7_leads.models import Lead
from app.modules.m8_outreach.models import OutreachSequence, OutreachStep
from app.modules.people_and_tenant.users.models import Employee, User
from app.modules.m8_outreach.schemas import (
    ApproveStepRequest,
    CreateSequenceRequest,
    OutreachSequenceResponse,
    OutreachSequenceSummary,
    OutreachStepResponse,
)

router = APIRouter(prefix="/m8", tags=["M8 - Outreach"])

M8 = Depends(require_module("M8"))


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_lead(
    lead_id: uuid.UUID,
    agency_id: uuid.UUID,
    db: AsyncSession,
) -> Lead:
    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.agency_id == agency_id,
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


async def _build_sequence_response(
    seq: OutreachSequence,
    db: AsyncSession,
) -> OutreachSequenceResponse:
    # Lead info
    lead_result = await db.execute(
        select(Lead).where(Lead.id == seq.lead_id)
    )
    lead = lead_result.scalar_one_or_none()
    lead_name = lead.full_name if lead else "Unknown"
    lead_company = lead.company_name if lead else "Unknown"

    # AE name
    assigned_to_name = None
    if seq.assigned_to:
        emp_result = await db.execute(
            select(Employee).where(Employee.id == seq.assigned_to)
        )
        emp = emp_result.scalar_one_or_none()
        if emp:
            user_result = await db.execute(
                select(User).where(User.id == emp.user_id)
            )
            user = user_result.scalar_one_or_none()
            assigned_to_name = user.full_name if user else None

    # Steps
    steps_result = await db.execute(
        select(OutreachStep).where(
            OutreachStep.sequence_id == seq.id
        ).order_by(OutreachStep.step_number)
    )
    steps = steps_result.scalars().all()
    step_responses = [OutreachStepResponse.model_validate(s) for s in steps]

    return OutreachSequenceResponse(
        id=seq.id,
        agency_id=seq.agency_id,
        lead_id=seq.lead_id,
        lead_name=lead_name,
        lead_company=lead_company,
        assigned_to=seq.assigned_to,
        assigned_to_name=assigned_to_name,
        status=seq.status,
        total_steps=seq.total_steps,
        current_step=seq.current_step,
        send_mode=seq.send_mode,
        icp_score_at_creation=seq.icp_score_at_creation,
        competitor_context_used=seq.competitor_context_used,
        replied_at=seq.replied_at,
        steps=step_responses,
        created_at=seq.created_at,
    )


# ── Create sequence ──────────────────────────────────────────────────────────

@router.post("/sequences", response_model=OutreachSequenceResponse, status_code=201)
async def create_outreach_sequence(
    body: CreateSequenceRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M8],
) -> OutreachSequenceResponse:
    """
    Generates a personalised outreach sequence for a lead.
    Pulls competitor context from Qdrant (M6) and lead data (M7).
    Returns immediately — sequence is generated in background.

    send_mode:
      manual — each step must be approved by AE before sending
      auto   — steps send automatically on schedule
    """
    lead = await _get_lead(body.lead_id, current_user.agency_id, db)

    # Check for existing active sequence for this lead
    existing = await db.execute(
        select(OutreachSequence).where(
            OutreachSequence.lead_id == lead.id,
            OutreachSequence.agency_id == current_user.agency_id,
            OutreachSequence.status.in_(["active", "paused"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            409,
            "An active sequence already exists for this lead. "
            "Pause or complete it before creating a new one.",
        )

    if body.assigned_to:
        emp_result = await db.execute(
            select(Employee).where(
                Employee.id == body.assigned_to,
                Employee.agency_id == current_user.agency_id,
            )
        )
        if not emp_result.scalar_one_or_none():
            raise HTTPException(404, "Employee not found in your agency")

    # Create a placeholder sequence so we can return immediately
    placeholder = OutreachSequence(
        agency_id=current_user.agency_id,
        lead_id=lead.id,
        assigned_to=body.assigned_to,
        status="active",
        total_steps=0,
        current_step=1,
        send_mode=body.send_mode,
    )
    db.add(placeholder)
    await db.commit()
    await db.refresh(placeholder)

    seq_id = str(placeholder.id)
    agency_id = str(current_user.agency_id)
    lead_id = str(lead.id)
    assigned_to_id = str(body.assigned_to) if body.assigned_to else None

    async def _run():
        # Delete placeholder and run full agent
        from app.modules.m8_outreach.agent import run_outreach_agent
        from app.database import AsyncSessionLocal
        from sqlalchemy import select as sel

        # Remove placeholder — agent creates the real sequence
        async with AsyncSessionLocal() as inner_db:
            result = await inner_db.execute(
                sel(OutreachSequence).where(
                    OutreachSequence.id == uuid.UUID(seq_id)
                )
            )
            seq = result.scalar_one_or_none()
            if seq and seq.total_steps == 0:
                await inner_db.delete(seq)
                await inner_db.commit()

        await run_outreach_agent(
            agency_id=agency_id,
            lead_id=lead_id,
            send_mode=body.send_mode,
            assigned_to_id=assigned_to_id,
        )

    background_tasks.add_task(_run)

    return await _build_sequence_response(placeholder, db)


# ── List sequences ────────────────────────────────────────────────────────────

@router.get("/sequences", response_model=list[OutreachSequenceSummary])
async def list_sequences(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M8],
    status: str | None = Query(None),
    lead_id: uuid.UUID | None = Query(None),
) -> list[OutreachSequenceSummary]:
    query = select(OutreachSequence).where(
        OutreachSequence.agency_id == current_user.agency_id
    )
    if status:
        query = query.where(OutreachSequence.status == status)
    if lead_id:
        query = query.where(OutreachSequence.lead_id == lead_id)
    query = query.order_by(OutreachSequence.created_at.desc())

    result = await db.execute(query)
    sequences = result.scalars().all()

    summaries = []
    for seq in sequences:
        lead_result = await db.execute(
            select(Lead).where(Lead.id == seq.lead_id)
        )
        lead = lead_result.scalar_one_or_none()

        summaries.append(OutreachSequenceSummary(
            id=seq.id,
            lead_id=seq.lead_id,
            lead_name=lead.full_name if lead else "Unknown",
            lead_company=lead.company_name if lead else "Unknown",
            status=seq.status,
            total_steps=seq.total_steps,
            current_step=seq.current_step,
            send_mode=seq.send_mode,
            icp_score_at_creation=seq.icp_score_at_creation,
            replied_at=seq.replied_at,
            created_at=seq.created_at,
        ))

    return summaries


# ── Get single sequence ───────────────────────────────────────────────────────

@router.get("/sequences/{sequence_id}", response_model=OutreachSequenceResponse)
async def get_sequence(
    sequence_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M8],
) -> OutreachSequenceResponse:
    result = await db.execute(
        select(OutreachSequence).where(
            OutreachSequence.id == sequence_id,
            OutreachSequence.agency_id == current_user.agency_id,
        )
    )
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(404, "Sequence not found")
    return await _build_sequence_response(seq, db)


# ── Get steps ────────────────────────────────────────────────────────────────

@router.get(
    "/sequences/{sequence_id}/steps",
    response_model=list[OutreachStepResponse],
)
async def get_sequence_steps(
    sequence_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M8],
) -> list[OutreachStepResponse]:
    # Verify ownership
    seq_result = await db.execute(
        select(OutreachSequence).where(
            OutreachSequence.id == sequence_id,
            OutreachSequence.agency_id == current_user.agency_id,
        )
    )
    if not seq_result.scalar_one_or_none():
        raise HTTPException(404, "Sequence not found")

    result = await db.execute(
        select(OutreachStep).where(
            OutreachStep.sequence_id == sequence_id
        ).order_by(OutreachStep.step_number)
    )
    steps = result.scalars().all()
    return [OutreachStepResponse.model_validate(s) for s in steps]


# ── Approve a step (manual mode) ─────────────────────────────────────────────

@router.post("/sequences/{sequence_id}/approve-step", response_model=OutreachStepResponse)
async def approve_step(
    sequence_id: uuid.UUID,
    body: ApproveStepRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M8],
) -> OutreachStepResponse:
    """
    AE approves a specific step in a manual-mode sequence.
    Once approved, the Celery scheduler will send it when due.
    """
    seq_result = await db.execute(
        select(OutreachSequence).where(
            OutreachSequence.id == sequence_id,
            OutreachSequence.agency_id == current_user.agency_id,
        )
    )
    seq = seq_result.scalar_one_or_none()
    if not seq:
        raise HTTPException(404, "Sequence not found")

    step_result = await db.execute(
        select(OutreachStep).where(
            OutreachStep.id == body.step_id,
            OutreachStep.sequence_id == sequence_id,
        )
    )
    step = step_result.scalar_one_or_none()
    if not step:
        raise HTTPException(404, "Step not found in this sequence")

    if step.status != "pending":
        raise HTTPException(
            400,
            f"Step is already {step.status} — can only approve pending steps",
        )

    step.approved_by_ae = True
    await db.commit()
    await db.refresh(step)
    return OutreachStepResponse.model_validate(step)


# ── Send next step manually ───────────────────────────────────────────────────

@router.post("/sequences/{sequence_id}/send-next", status_code=202)
async def send_next_step(
    sequence_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M8],
) -> dict:
    """
    Owner manually triggers the next pending step immediately,
    without waiting for the scheduled time.
    """
    seq_result = await db.execute(
        select(OutreachSequence).where(
            OutreachSequence.id == sequence_id,
            OutreachSequence.agency_id == current_user.agency_id,
        )
    )
    seq = seq_result.scalar_one_or_none()
    if not seq:
        raise HTTPException(404, "Sequence not found")

    if seq.status != "active":
        raise HTTPException(
            400,
            f"Sequence is {seq.status} — can only send from active sequences",
        )

    # Get current pending step
    step_result = await db.execute(
        select(OutreachStep).where(
            OutreachStep.sequence_id == sequence_id,
            OutreachStep.step_number == seq.current_step,
            OutreachStep.status == "pending",
        )
    )
    step = step_result.scalar_one_or_none()
    if not step:
        raise HTTPException(
            404,
            f"No pending step found at position {seq.current_step}",
        )

    # Approve and trigger immediately
    step.approved_by_ae = True
    step.scheduled_send_at = datetime.now(timezone.utc)
    await db.commit()

    async def _trigger():
        from app.modules.m8_outreach.tasks import send_scheduled_steps
        send_scheduled_steps.apply_async()

    background_tasks.add_task(_trigger)

    return {
        "status": "triggered",
        "step_number": step.step_number,
        "channel": step.channel,
        "message": "Step will send within seconds.",
    }


# ── Pause sequence ────────────────────────────────────────────────────────────

@router.patch("/sequences/{sequence_id}/pause", response_model=OutreachSequenceResponse)
async def pause_sequence(
    sequence_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M8],
) -> OutreachSequenceResponse:
    result = await db.execute(
        select(OutreachSequence).where(
            OutreachSequence.id == sequence_id,
            OutreachSequence.agency_id == current_user.agency_id,
        )
    )
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(404, "Sequence not found")

    if seq.status != "active":
        raise HTTPException(400, f"Cannot pause a {seq.status} sequence")

    seq.status = "paused"
    await db.commit()
    await db.refresh(seq)
    return await _build_sequence_response(seq, db)


# ── Resume sequence ───────────────────────────────────────────────────────────

@router.patch("/sequences/{sequence_id}/resume", response_model=OutreachSequenceResponse)
async def resume_sequence(
    sequence_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M8],
) -> OutreachSequenceResponse:
    result = await db.execute(
        select(OutreachSequence).where(
            OutreachSequence.id == sequence_id,
            OutreachSequence.agency_id == current_user.agency_id,
        )
    )
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(404, "Sequence not found")

    if seq.status != "paused":
        raise HTTPException(400, f"Cannot resume a {seq.status} sequence")

    seq.status = "active"
    await db.commit()
    await db.refresh(seq)
    return await _build_sequence_response(seq, db)


# ── Webhook: Gmail reply detected ─────────────────────────────────────────────

@router.post("/webhooks/reply", status_code=200)
async def reply_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    n8n calls this when Gmail polling detects a reply to an outreach email.
    Matches the reply to a sequence by from_email, marks it replied,
    and stops further steps from sending.

    Expected payload:
    {
      "gmail_message_id": "...",
      "from_email": "...",
      "subject": "Re: ...",
      "body": "..."
    }
    """
    payload = await request.json()

    from_email = payload.get("from_email", "").lower().strip()
    gmail_message_id = payload.get("gmail_message_id")

    if not from_email:
        return {"status": "ignored", "reason": "missing from_email"}

    # Find lead by email
    lead_result = await db.execute(
        select(Lead).where(Lead.email == from_email)
    )
    lead = lead_result.scalar_one_or_none()

    if not lead:
        return {"status": "unmatched", "from_email": from_email}

    # Find active sequence for this lead
    seq_result = await db.execute(
        select(OutreachSequence).where(
            OutreachSequence.lead_id == lead.id,
            OutreachSequence.status.in_(["active", "paused"]),
        )
    )
    seq = seq_result.scalar_one_or_none()

    if not seq:
        return {"status": "no_active_sequence", "lead_id": str(lead.id)}

    # Mark sequence as replied
    seq.status = "replied"
    seq.replied_at = datetime.now(timezone.utc)
    seq.reply_gmail_message_id = gmail_message_id

    await db.commit()

    # Notify AE of reply
    logger.info("[Outreach] Reply received from %s — sequence paused", from_email)
    logger.warning(
        "[SLACK STUB] 📩 Reply from %s (%s) — sequence stopped. "
        "Follow up personally.",
        lead.full_name,
        lead.company_name,
    )

    return {
        "status": "reply_recorded",
        "lead_id": str(lead.id),
        "sequence_id": str(seq.id),
    }


import logging
logger = logging.getLogger(__name__)