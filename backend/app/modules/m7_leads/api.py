import json
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_module, require_owner
from app.database import get_db
from app.modules.m7_leads.models import IcpProfile, Lead, LeadScore
from app.modules.people_and_tenant.users.models import Employee, User
from app.modules.m7_leads.schemas import (
    IcpProfileCreate,
    IcpProfileResponse,
    LeadCreate,
    LeadResponse,
    LeadScoreResponse,
    LeadStatusUpdate,
    LeadSummary,
)

router = APIRouter(prefix="/m7", tags=["M7 - Lead Analyst"])

M7 = Depends(require_module("M7"))


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


async def _build_lead_response(
    lead: Lead,
    db: AsyncSession,
) -> LeadResponse:
    assigned_name = await _get_assigned_name(lead.assigned_to, db)

    score_data = None
    if lead.score:
        try:
            strengths = json.loads(lead.score.strengths_json)
        except Exception:
            strengths = []
        try:
            concerns = json.loads(lead.score.concerns_json)
        except Exception:
            concerns = []

        score_data = LeadScoreResponse(
            score=lead.score.score,
            rationale=lead.score.rationale or "",
            strengths=strengths,
            concerns=concerns,
            next_action=lead.score.next_action or "",
            hubspot_updated=lead.score.hubspot_updated,
            created_at=lead.score.created_at,
        )

    return LeadResponse(
        id=lead.id,
        agency_id=lead.agency_id,
        full_name=lead.full_name,
        email=lead.email,
        phone=lead.phone,
        designation=lead.designation,
        company_name=lead.company_name,
        company_size=lead.company_size,
        industry=lead.industry,
        website=lead.website,
        monthly_ad_budget=lead.monthly_ad_budget,
        pain_points=lead.pain_points,
        notes=lead.notes,
        source=lead.source,
        status=lead.status,
        hubspot_deal_id=lead.hubspot_deal_id,
        assigned_to=lead.assigned_to,
        assigned_to_name=assigned_name,
        score_data=score_data,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


# ── ICP: Define / Update ─────────────────────────────────────────────────────

@router.post("/icp", response_model=IcpProfileResponse)
async def upsert_icp(
    body: IcpProfileCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M7],
) -> IcpProfileResponse:
    """
    Creates or updates the agency's Ideal Client Profile.
    Uses natural language descriptions — Claude reads these
    directly when scoring leads.
    """
    existing = await db.execute(
        select(IcpProfile).where(
            IcpProfile.agency_id == current_user.agency_id
        )
    )
    icp = existing.scalar_one_or_none()

    if icp:
        for field, value in body.model_dump().items():
            setattr(icp, field, value)
    else:
        icp = IcpProfile(
            agency_id=current_user.agency_id,
            **body.model_dump(),
        )
        db.add(icp)

    await db.commit()
    await db.refresh(icp)
    return IcpProfileResponse.model_validate(icp)


# ── ICP: Get ─────────────────────────────────────────────────────────────────

@router.get("/icp", response_model=IcpProfileResponse)
async def get_icp(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M7],
) -> IcpProfileResponse:
    result = await db.execute(
        select(IcpProfile).where(
            IcpProfile.agency_id == current_user.agency_id
        )
    )
    icp = result.scalar_one_or_none()
    if not icp:
        raise HTTPException(
            404,
            "No ICP defined yet. Create one with POST /m7/icp",
        )
    return IcpProfileResponse.model_validate(icp)


# ── Leads: Create ────────────────────────────────────────────────────────────

@router.post("/leads", response_model=LeadResponse, status_code=201)
async def create_lead(
    body: LeadCreate,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M7],
) -> LeadResponse:
    """
    Owner manually adds a lead.
    Scoring agent runs immediately in background.
    """
    # Check for duplicate email in this agency
    existing = await db.execute(
        select(Lead).where(
            Lead.email == body.email.lower(),
            Lead.agency_id == current_user.agency_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            409,
            f"Lead with email {body.email} already exists"
        )

    # Validate assigned employee
    if body.assigned_to:
        emp_result = await db.execute(
            select(Employee).where(
                Employee.id == body.assigned_to,
                Employee.agency_id == current_user.agency_id,
            )
        )
        if not emp_result.scalar_one_or_none():
            raise HTTPException(404, "Employee not found in your agency")

    lead_data = body.model_dump()
    lead_data["email"] = lead_data["email"].lower()

    lead = Lead(
        agency_id=current_user.agency_id,
        **lead_data,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    # Score in background
    lead_id = str(lead.id)
    agency_id = str(current_user.agency_id)

    async def _score():
        from app.modules.m7_leads.agent import run_lead_agent
        await run_lead_agent(lead_id=lead_id, agency_id=agency_id)

    background_tasks.add_task(_score)

    return await _build_lead_response(lead, db)


# ── Leads: List ──────────────────────────────────────────────────────────────

@router.get("/leads", response_model=list[LeadSummary])
async def list_leads(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M7],
    status: str | None = Query(None),
    min_score: float | None = Query(None, ge=0, le=100),
    source: str | None = Query(None),
    assigned_to: uuid.UUID | None = Query(None),
) -> list[LeadSummary]:
    """
    Lists all leads sorted by ICP score descending.
    Highest-scoring leads appear first.
    """
    query = select(Lead).where(
        Lead.agency_id == current_user.agency_id
    )
    if status:
        query = query.where(Lead.status == status)
    if source:
        query = query.where(Lead.source == source)
    if assigned_to:
        query = query.where(Lead.assigned_to == assigned_to)

    result = await db.execute(query)
    leads = result.scalars().all()

    # Build summaries with score
    summaries = []
    for lead in leads:
        icp_score = None
        if lead.score:
            icp_score = lead.score.score
            if min_score is not None and icp_score < min_score:
                continue

        assigned_name = await _get_assigned_name(lead.assigned_to, db)

        summaries.append(LeadSummary(
            id=lead.id,
            full_name=lead.full_name,
            company_name=lead.company_name,
            industry=lead.industry,
            source=lead.source,
            status=lead.status,
            icp_score=icp_score,
            assigned_to_name=assigned_name,
            created_at=lead.created_at,
        ))

    # Sort by score descending — unscored leads go to bottom
    summaries.sort(
        key=lambda x: x.icp_score if x.icp_score is not None else -1,
        reverse=True,
    )

    return summaries


# ── Leads: Get one ───────────────────────────────────────────────────────────

@router.get("/leads/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M7],
) -> LeadResponse:
    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.agency_id == current_user.agency_id,
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found")

    # Eager load score
    if lead.score is None:
        await db.refresh(lead, ["score"])

    return await _build_lead_response(lead, db)


# ── Leads: Re-score ──────────────────────────────────────────────────────────

@router.post("/leads/{lead_id}/score", status_code=202)
async def rescore_lead(
    lead_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M7],
) -> dict:
    """
    Re-runs the scoring agent for a lead.
    Useful after updating the ICP or after adding more lead info.
    """
    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.agency_id == current_user.agency_id,
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found")

    lead_id_str = str(lead.id)
    agency_id_str = str(current_user.agency_id)

    async def _score():
        from app.modules.m7_leads.agent import run_lead_agent
        await run_lead_agent(
            lead_id=lead_id_str,
            agency_id=agency_id_str,
        )

    background_tasks.add_task(_score)

    return {
        "status": "scoring_started",
        "lead_id": lead_id_str,
        "message": "Re-scoring in background. Check GET /m7/leads/{id} in ~15 seconds.",
    }


# ── Leads: Update status ─────────────────────────────────────────────────────

@router.patch("/leads/{lead_id}/status", response_model=LeadResponse)
async def update_lead_status(
    lead_id: uuid.UUID,
    body: LeadStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M7],
) -> LeadResponse:
    result = await db.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.agency_id == current_user.agency_id,
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found")

    lead.status = body.status
    await db.commit()
    await db.refresh(lead, ["score"])
    return await _build_lead_response(lead, db)


# ── Webhook: HubSpot lead intake ──────────────────────────────────────────────

@router.post("/webhooks/hubspot-lead", status_code=200)
async def hubspot_lead_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    n8n calls this when a new lead arrives in HubSpot
    (form fill, deal import, or manual entry).

    Expected payload from n8n:
    {
      "agency_id": "...",
      "full_name": "...",
      "email": "...",
      "company_name": "...",
      "designation": "...",
      "industry": "...",
      "monthly_ad_budget": "...",
      "pain_points": "...",
      "hubspot_contact_id": "...",
      "hubspot_deal_id": "..."
    }
    """
    payload = await request.json()

    agency_id_str = payload.get("agency_id")
    if not agency_id_str:
        return {"status": "ignored", "reason": "missing agency_id"}

    email = payload.get("email", "").lower().strip()
    full_name = payload.get("full_name", "Unknown")
    company_name = payload.get("company_name", "Unknown")

    if not email or not company_name:
        return {"status": "ignored", "reason": "missing email or company_name"}

    agency_id = uuid.UUID(agency_id_str)

    # Deduplicate
    existing = await db.execute(
        select(Lead).where(
            Lead.email == email,
            Lead.agency_id == agency_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "email": email}

    lead = Lead(
        agency_id=agency_id,
        full_name=full_name,
        email=email,
        phone=payload.get("phone"),
        designation=payload.get("designation"),
        company_name=company_name,
        company_size=payload.get("company_size"),
        industry=payload.get("industry"),
        website=payload.get("website"),
        monthly_ad_budget=payload.get("monthly_ad_budget"),
        pain_points=payload.get("pain_points"),
        source="hubspot",
        hubspot_deal_id=payload.get("hubspot_deal_id"),
        hubspot_contact_id=payload.get("hubspot_contact_id"),
        status="new",
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    lead_id_str = str(lead.id)

    async def _score():
        from app.modules.m7_leads.agent import run_lead_agent
        await run_lead_agent(
            lead_id=lead_id_str,
            agency_id=agency_id_str,
        )

    background_tasks.add_task(_score)

    return {
        "status": "lead_created",
        "lead_id": lead_id_str,
        "scoring": "started_in_background",
    }