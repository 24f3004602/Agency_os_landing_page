import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_module, require_owner
from app.core.buffer import schedule_post
from app.config import settings
from app.database import get_db
from app.modules.m11_content.models import (
    ClientApprovalRequest,
    ContentBrief,
    ContentDraft,
)
from app.modules.people_and_tenant.users.models import Client, User, UserRole
from app.modules.m11_content.schemas import (
    ApprovalActionRequest,
    ApprovalRequestResponse,
    ContentBriefCreate,
    ContentBriefResponse,
    ContentBriefSummary,
    ContentDraftResponse,
    ContentPipelineItem,
    SubmitForApprovalRequest,
)

router = APIRouter(prefix="/m11", tags=["M11 - Campaign Orchestration"])

M11 = Depends(require_module("M11"))


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_client(
    client_id: uuid.UUID,
    agency_id: uuid.UUID,
    db: AsyncSession,
) -> Client:
    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.agency_id == agency_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Client not found")
    return client


async def _build_brief_response(
    brief: ContentBrief,
    db: AsyncSession,
) -> ContentBriefResponse:
    client_result = await db.execute(
        select(Client).where(Client.id == brief.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"

    drafts_result = await db.execute(
        select(ContentDraft).where(
            ContentDraft.brief_id == brief.id
        ).order_by(ContentDraft.variation_number)
    )
    drafts = drafts_result.scalars().all()
    draft_responses = [ContentDraftResponse.model_validate(d) for d in drafts]

    return ContentBriefResponse(
        id=brief.id,
        agency_id=brief.agency_id,
        client_id=brief.client_id,
        client_name=client_name,
        campaign_id=brief.campaign_id,
        title=brief.title,
        objective=brief.objective,
        target_audience=brief.target_audience,
        key_message=brief.key_message,
        tone_of_voice=brief.tone_of_voice,
        platform=brief.platform,
        content_type=brief.content_type,
        word_limit=brief.word_limit,
        num_variations=brief.num_variations,
        status=brief.status,
        drafts=draft_responses,
        created_at=brief.created_at,
        updated_at=brief.updated_at,
    )


async def _build_approval_response(
    approval: ClientApprovalRequest,
    db: AsyncSession,
) -> ApprovalRequestResponse:
    client_result = await db.execute(
        select(Client).where(Client.id == approval.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"

    draft_result = await db.execute(
        select(ContentDraft).where(ContentDraft.id == approval.draft_id)
    )
    draft = draft_result.scalar_one_or_none()
    draft_angle = draft.angle if draft else None
    draft_preview = (draft.body_copy[:150] + "...") if draft and len(draft.body_copy) > 150 else (draft.body_copy if draft else "")

    brief_title = ""
    if draft:
        brief_result = await db.execute(
            select(ContentBrief).where(ContentBrief.id == draft.brief_id)
        )
        brief = brief_result.scalar_one_or_none()
        brief_title = brief.title if brief else ""

    return ApprovalRequestResponse(
        id=approval.id,
        draft_id=approval.draft_id,
        client_id=approval.client_id,
        client_name=client_name,
        brief_title=brief_title,
        draft_angle=draft_angle,
        draft_body_preview=draft_preview,
        status=approval.status,
        sent_via=approval.sent_via,
        responded_at=approval.responded_at,
        response_channel=approval.response_channel,
        client_feedback=approval.client_feedback,
        reminder_count=approval.reminder_count,
        created_at=approval.created_at,
    )


# ── Briefs: Create ────────────────────────────────────────────────────────────

@router.post("/briefs", response_model=ContentBriefResponse, status_code=201)
async def create_brief(
    body: ContentBriefCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M11],
) -> ContentBriefResponse:
    """
    Owner or employee creates a content brief.
    This does NOT trigger generation yet — call POST /m11/briefs/{id}/generate
    when ready to produce drafts.
    """
    await _get_client(body.client_id, current_user.agency_id, db)

    brief = ContentBrief(
        agency_id=current_user.agency_id,
        client_id=body.client_id,
        campaign_id=body.campaign_id,
        campaign_task_id=body.campaign_task_id,
        title=body.title,
        objective=body.objective,
        target_audience=body.target_audience,
        key_message=body.key_message,
        tone_of_voice=body.tone_of_voice,
        platform=body.platform,
        content_type=body.content_type,
        word_limit=body.word_limit,
        reference_urls=body.reference_urls,
        additional_notes=body.additional_notes,
        num_variations=body.num_variations,
        created_by=current_user.id,
        status="draft",
    )
    db.add(brief)
    await db.commit()
    await db.refresh(brief)
    return await _build_brief_response(brief, db)


# ── Briefs: List ──────────────────────────────────────────────────────────────

@router.get("/briefs", response_model=list[ContentBriefSummary])
async def list_briefs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M11],
    client_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    platform: str | None = Query(None),
) -> list[ContentBriefSummary]:
    query = select(ContentBrief).where(
        ContentBrief.agency_id == current_user.agency_id
    )
    if client_id:
        query = query.where(ContentBrief.client_id == client_id)
    if status:
        query = query.where(ContentBrief.status == status)
    if platform:
        query = query.where(ContentBrief.platform == platform)
    query = query.order_by(ContentBrief.created_at.desc())

    result = await db.execute(query)
    briefs = result.scalars().all()

    summaries = []
    for brief in briefs:
        client_result = await db.execute(
            select(Client).where(Client.id == brief.client_id)
        )
        client = client_result.scalar_one_or_none()

        drafts_result = await db.execute(
            select(ContentDraft).where(ContentDraft.brief_id == brief.id)
        )
        drafts = drafts_result.scalars().all()

        summaries.append(ContentBriefSummary(
            id=brief.id,
            client_id=brief.client_id,
            client_name=client.company_name if client else "Unknown",
            title=brief.title,
            platform=brief.platform,
            content_type=brief.content_type,
            status=brief.status,
            num_variations=brief.num_variations,
            draft_count=len(drafts),
            created_at=brief.created_at,
        ))

    return summaries


# ── Briefs: Get one ───────────────────────────────────────────────────────────

@router.get("/briefs/{brief_id}", response_model=ContentBriefResponse)
async def get_brief(
    brief_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M11],
) -> ContentBriefResponse:
    result = await db.execute(
        select(ContentBrief).where(
            ContentBrief.id == brief_id,
            ContentBrief.agency_id == current_user.agency_id,
        )
    )
    brief = result.scalar_one_or_none()
    if not brief:
        raise HTTPException(404, "Brief not found")
    return await _build_brief_response(brief, db)


# ── Briefs: Trigger generation ────────────────────────────────────────────────

@router.post("/briefs/{brief_id}/generate", status_code=202)
async def generate_drafts(
    brief_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M11],
) -> dict:
    """
    Triggers Claude to generate content drafts for this brief.
    Returns 202 — drafts appear in GET /m11/briefs/{id} after ~30 seconds.
    """
    result = await db.execute(
        select(ContentBrief).where(
            ContentBrief.id == brief_id,
            ContentBrief.agency_id == current_user.agency_id,
        )
    )
    brief = result.scalar_one_or_none()
    if not brief:
        raise HTTPException(404, "Brief not found")

    if brief.status in ("generating",):
        raise HTTPException(409, "Generation already in progress")

    brief_id_str = str(brief_id)
    agency_id_str = str(current_user.agency_id)

    async def _run():
        from app.modules.m11_content.agent import run_content_agent
        await run_content_agent(
            brief_id=brief_id_str,
            agency_id=agency_id_str,
        )

    background_tasks.add_task(_run)

    return {
        "status": "generation_started",
        "brief_id": brief_id_str,
        "num_variations": brief.num_variations,
        "message": (
            f"Generating {brief.num_variations} variation(s). "
            f"Check GET /m11/briefs/{brief_id} in ~30 seconds."
        ),
    }


# ── Drafts: Get one ───────────────────────────────────────────────────────────

@router.get("/drafts/{draft_id}", response_model=ContentDraftResponse)
async def get_draft(
    draft_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ContentDraftResponse:
    """Clients can view drafts sent for their approval."""
    result = await db.execute(
        select(ContentDraft).where(ContentDraft.id == draft_id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Draft not found")

    # Verify agency access
    if draft.agency_id != current_user.agency_id:
        raise HTTPException(403, "Access denied")

    return ContentDraftResponse.model_validate(draft)


# ── Approvals: Submit a draft for client review ───────────────────────────────

@router.post("/approvals/submit", response_model=ApprovalRequestResponse, status_code=201)
async def submit_for_approval(
    body: SubmitForApprovalRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M11],
) -> ApprovalRequestResponse:
    """
    Owner selects a specific draft and sends it to the client for approval.
    Creates a ClientApprovalRequest and notifies the client.
    """
    draft_result = await db.execute(
        select(ContentDraft).where(
            ContentDraft.id == body.draft_id,
            ContentDraft.agency_id == current_user.agency_id,
        )
    )
    draft = draft_result.scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Draft not found")

    if draft.status not in ("generated", "selected"):
        raise HTTPException(
            400,
            f"Draft must be in 'generated' status to submit. "
            f"Current: {draft.status}",
        )

    # Check not already submitted
    existing_approval = await db.execute(
        select(ClientApprovalRequest).where(
            ClientApprovalRequest.draft_id == body.draft_id
        )
    )
    if existing_approval.scalar_one_or_none():
        raise HTTPException(409, "An approval request already exists for this draft")

    # Get brief + client
    brief_result = await db.execute(
        select(ContentBrief).where(ContentBrief.id == draft.brief_id)
    )
    brief = brief_result.scalar_one_or_none()
    if not brief:
        raise HTTPException(404, "Brief not found")

    client = await _get_client(brief.client_id, current_user.agency_id, db)

    # Create approval request
    approval = ClientApprovalRequest(
        draft_id=draft.id,
        agency_id=current_user.agency_id,
        client_id=client.id,
        status="pending",
        sent_via=body.send_via,
    )
    db.add(approval)
    draft.status = "submitted"
    brief.status = "submitted"

    await db.commit()
    await db.refresh(approval)

    # Send WhatsApp notification
    if body.send_via in ("whatsapp", "both") and client.contact_phone:
        from app.core.wati import send_whatsapp_message
        try:
            await send_whatsapp_message(
                phone_number=client.contact_phone,
                message=(
                    f"Hi {client.contact_name or client.company_name}! 👋\n\n"
                    f"A new content draft is ready for your approval:\n"
                    f"*{brief.title}*\n\n"
                    f"Preview: {draft.body_copy[:100]}...\n\n"
                    f"Reply *APPROVE* to approve or *REJECT* with your feedback."
                ),
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "WhatsApp notification failed: %s", e
            )

    return await _build_approval_response(approval, db)


# ── Approvals: List ───────────────────────────────────────────────────────────

@router.get("/approvals", response_model=list[ApprovalRequestResponse])
async def list_approvals(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M11],
    status: str | None = Query(None),
    client_id: uuid.UUID | None = Query(None),
) -> list[ApprovalRequestResponse]:
    """Lists approval requests. Default: pending only."""
    query = select(ClientApprovalRequest).where(
        ClientApprovalRequest.agency_id == current_user.agency_id
    )
    if status:
        query = query.where(ClientApprovalRequest.status == status)
    else:
        query = query.where(ClientApprovalRequest.status == "pending")
    if client_id:
        query = query.where(ClientApprovalRequest.client_id == client_id)
    query = query.order_by(ClientApprovalRequest.created_at.desc())

    result = await db.execute(query)
    approvals = result.scalars().all()

    return [await _build_approval_response(a, db) for a in approvals]


# ── Approvals: Approve ────────────────────────────────────────────────────────

@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRequestResponse)
async def approve_content(
    approval_id: uuid.UUID,
    body: ApprovalActionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApprovalRequestResponse:
    """
    Client or owner approves the content.
    Triggers automatic Buffer scheduling if credentials configured.
    Updates M5 campaign task status if linked.
    """
    result = await db.execute(
        select(ClientApprovalRequest).where(
            ClientApprovalRequest.id == approval_id,
            ClientApprovalRequest.agency_id == current_user.agency_id,
        )
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(404, "Approval request not found")

    if approval.status != "pending":
        raise HTTPException(
            400,
            f"This request is already {approval.status}",
        )

    now = datetime.now(timezone.utc)
    approval.status = "approved"
    approval.responded_at = now
    approval.response_channel = (
        "portal" if current_user.role != UserRole.CLIENT else "portal"
    )

    # Update draft status
    draft_result = await db.execute(
        select(ContentDraft).where(ContentDraft.id == approval.draft_id)
    )
    draft = draft_result.scalar_one_or_none()

    if draft:
        draft.status = "approved"

        # Schedule via Buffer
        try:
            buffer_result = await schedule_post(
                content=draft.body_copy,
                profile_id=settings.buffer_default_profile_id or "default",
                scheduled_at=None,
            )
            draft.buffer_post_id = buffer_result.get("id")
            draft.status = "published"
            draft.published_at = now
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Buffer scheduling failed: %s", e
            )

        # Update brief status
        brief_result = await db.execute(
            select(ContentBrief).where(ContentBrief.id == draft.brief_id)
        )
        brief = brief_result.scalar_one_or_none()
        if brief:
            brief.status = "published"

            # Update linked M5 campaign task if exists
            if brief.campaign_task_id:
                from app.modules.m5_campaigns.models import CampaignTask
                task_result = await db.execute(
                    select(CampaignTask).where(
                        CampaignTask.id == brief.campaign_task_id
                    )
                )
                task = task_result.scalar_one_or_none()
                if task:
                    task.status = "scheduled"
                    import logging
                    logging.getLogger(__name__).info(
                        "M5 campaign task %s updated to scheduled", task.id
                    )

    await db.commit()
    await db.refresh(approval)

    import logging
    logging.getLogger(__name__).warning(
        "[SLACK STUB] ✅ Content approved by client %s — scheduling via Buffer",
        current_user.agency_id,
    )

    return await _build_approval_response(approval, db)


# ── Approvals: Reject ─────────────────────────────────────────────────────────

@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRequestResponse)
async def reject_content(
    approval_id: uuid.UUID,
    body: ApprovalActionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApprovalRequestResponse:
    """
    Client rejects the content and provides feedback.
    Owner/AM will need to revise and resubmit.
    """
    if not body.feedback:
        raise HTTPException(
            400,
            "Feedback is required when rejecting content",
        )

    result = await db.execute(
        select(ClientApprovalRequest).where(
            ClientApprovalRequest.id == approval_id,
            ClientApprovalRequest.agency_id == current_user.agency_id,
        )
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(404, "Approval request not found")

    if approval.status != "pending":
        raise HTTPException(400, f"Request is already {approval.status}")

    now = datetime.now(timezone.utc)
    approval.status = "rejected"
    approval.responded_at = now
    approval.response_channel = "portal"
    approval.client_feedback = body.feedback

    # Update draft
    draft_result = await db.execute(
        select(ContentDraft).where(ContentDraft.id == approval.draft_id)
    )
    draft = draft_result.scalar_one_or_none()
    if draft:
        draft.status = "rejected"
        draft.rejection_feedback = body.feedback

    # Revert brief to ready so new draft can be submitted
    if draft:
        brief_result = await db.execute(
            select(ContentBrief).where(ContentBrief.id == draft.brief_id)
        )
        brief = brief_result.scalar_one_or_none()
        if brief:
            brief.status = "ready"

    await db.commit()
    await db.refresh(approval)

    import logging
    logging.getLogger(__name__).warning(
        "[SLACK STUB] ❌ Content rejected by client. Feedback: %s",
        body.feedback[:100],
    )

    return await _build_approval_response(approval, db)


# ── Webhook: WhatsApp approval reply ─────────────────────────────────────────

@router.post("/webhooks/approval", status_code=200)
async def whatsapp_approval_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    n8n calls this when a client replies to an approval WhatsApp message.
    Detects APPROVE or REJECT keywords and processes accordingly.

    Expected payload from n8n:
    {
      "from_phone": "+919876543210",
      "message": "APPROVE" or "REJECT - please make it shorter"
    }
    """
    payload = await request.json()

    from_phone = payload.get("from_phone", "").strip()
    message = payload.get("message", "").strip().upper()

    if not from_phone or not message:
        return {"status": "ignored", "reason": "missing phone or message"}

    # Find client by phone
    client_result = await db.execute(
        select(Client).where(Client.contact_phone == from_phone)
    )
    client = client_result.scalar_one_or_none()

    if not client:
        return {"status": "unmatched", "phone": from_phone}

    # Find latest pending approval for this client
    approval_result = await db.execute(
        select(ClientApprovalRequest).where(
            ClientApprovalRequest.client_id == client.id,
            ClientApprovalRequest.status == "pending",
        ).order_by(ClientApprovalRequest.created_at.desc()).limit(1)
    )
    approval = approval_result.scalar_one_or_none()

    if not approval:
        return {
            "status": "no_pending_approval",
            "client_id": str(client.id),
        }

    now = datetime.now(timezone.utc)

    if message.startswith("APPROVE"):
        approval.status = "approved"
        approval.responded_at = now
        approval.response_channel = "whatsapp"

        # Update draft
        draft_result = await db.execute(
            select(ContentDraft).where(ContentDraft.id == approval.draft_id)
        )
        draft = draft_result.scalar_one_or_none()
        if draft:
            draft.status = "approved"

        await db.commit()
        return {"status": "approved", "approval_id": str(approval.id)}

    elif message.startswith("REJECT"):
        # Extract feedback after "REJECT "
        original_message = payload.get("message", "").strip()
        feedback = original_message[6:].strip() if len(original_message) > 6 else "No feedback provided"

        approval.status = "rejected"
        approval.responded_at = now
        approval.response_channel = "whatsapp"
        approval.client_feedback = feedback

        draft_result = await db.execute(
            select(ContentDraft).where(ContentDraft.id == approval.draft_id)
        )
        draft = draft_result.scalar_one_or_none()
        if draft:
            draft.status = "rejected"
            draft.rejection_feedback = feedback

        await db.commit()
        return {
            "status": "rejected",
            "approval_id": str(approval.id),
            "feedback": feedback,
        }

    return {"status": "unrecognised", "message": payload.get("message")}


# ── Pipeline view ─────────────────────────────────────────────────────────────

@router.get("/pipeline/{client_id}", response_model=list[ContentPipelineItem])
async def get_content_pipeline(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M11],
) -> list[ContentPipelineItem]:
    """
    Full content pipeline for a client.
    Shows every brief and their current status,
    draft counts, and approval/publish stats.
    """
    await _get_client(client_id, current_user.agency_id, db)

    briefs_result = await db.execute(
        select(ContentBrief).where(
            ContentBrief.client_id == client_id,
            ContentBrief.agency_id == current_user.agency_id,
        ).order_by(ContentBrief.created_at.desc())
    )
    briefs = briefs_result.scalars().all()

    items = []
    for brief in briefs:
        drafts_result = await db.execute(
            select(ContentDraft).where(ContentDraft.brief_id == brief.id)
        )
        drafts = drafts_result.scalars().all()

        pending_approvals = sum(
            1 for d in drafts if d.status == "submitted"
        )
        approved_count = sum(
            1 for d in drafts if d.status in ("approved", "published")
        )
        published_count = sum(
            1 for d in drafts if d.status == "published"
        )

        items.append(ContentPipelineItem(
            brief_id=brief.id,
            title=brief.title,
            platform=brief.platform,
            content_type=brief.content_type,
            status=brief.status,
            draft_count=len(drafts),
            pending_approvals=pending_approvals,
            approved_count=approved_count,
            published_count=published_count,
            created_at=brief.created_at,
        ))

    return items