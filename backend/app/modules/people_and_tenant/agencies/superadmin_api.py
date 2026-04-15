import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_superadmin
from app.core.security import hash_password
from app.database import get_db
from app.modules.people_and_tenant.agencies.models import Agency, AgencyModule, MODULE_DEPENDENCIES
from app.modules.people_and_tenant.users.models import User, UserRole

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class CreateAgencyRequest(BaseModel):
    agency_name: str = Field(..., min_length=1, max_length=255)
    owner_full_name: str = Field(..., min_length=1, max_length=255)
    owner_email: EmailStr
    owner_password: str = Field(..., min_length=8)
    owner_phone: str | None = None
    plan_tier: str = "trial"
    modules_to_activate: list[str] = ["M1"]  # at minimum M1


class AgencyCreatedResponse(BaseModel):
    agency_id: uuid.UUID
    owner_user_id: uuid.UUID
    agency_name: str
    owner_email: str
    modules_activated: list[str]
    message: str


# ── Create Agency + Owner ────────────────────────────────────────────────────

@router.post("/agencies", response_model=AgencyCreatedResponse, status_code=201)
async def create_agency(
    body: CreateAgencyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_superadmin)],
) -> AgencyCreatedResponse:
    """
    SuperAdmin creates a new agency and its owner account in one shot.
    Validates module dependencies before activating requested modules.
    """
    # Check email not already taken
    existing = await db.execute(
        select(User).where(User.email == body.owner_email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Email {body.owner_email} is already registered")

    # Validate module dependency order
    # e.g. can't activate M3 without M2 and M1
    requested = set(body.modules_to_activate)
    for module in requested:
        if module not in MODULE_DEPENDENCIES:
            raise HTTPException(400, f"Unknown module: {module}")
        for dep in MODULE_DEPENDENCIES[module]:
            if dep not in requested:
                raise HTTPException(
                    400,
                    f"Module {module} requires {dep} to also be activated"
                )

    # Create agency
    agency = Agency(
        name=body.agency_name,
        owner_email=body.owner_email.lower(),
        owner_phone=body.owner_phone,
        plan_tier=body.plan_tier,
        status="trial",
    )
    db.add(agency)
    await db.flush()  # get agency.id

    # Create owner user
    owner = User(
        email=body.owner_email.lower(),
        password_hash=hash_password(body.owner_password),
        full_name=body.owner_full_name,
        role=UserRole.OWNER,
        agency_id=agency.id,
        is_active=True,
    )
    db.add(owner)

    # Activate requested modules
    now = datetime.now(timezone.utc)
    for module_code in requested:
        db.add(AgencyModule(
            agency_id=agency.id,
            module_code=module_code,
            is_active=True,
            activated_at=now,
            activated_by="superadmin",
        ))

    await db.commit()
    await db.refresh(agency)
    await db.refresh(owner)

    return AgencyCreatedResponse(
        agency_id=agency.id,
        owner_user_id=owner.id,
        agency_name=agency.name,
        owner_email=owner.email,
        modules_activated=list(requested),
        message=f"Agency '{agency.name}' created. Owner can log in with their email and password.",
    )


# ── List all agencies ────────────────────────────────────────────────────────

class AgencySummary(BaseModel):
    id: uuid.UUID
    name: str
    owner_email: str
    status: str
    plan_tier: str
    active_modules: list[str]
    created_at: datetime


@router.get("/agencies", response_model=list[AgencySummary])
async def list_agencies(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_superadmin)],
) -> list[AgencySummary]:
    result = await db.execute(select(Agency).order_by(Agency.created_at.desc()))
    agencies = result.scalars().all()

    summaries = []
    for agency in agencies:
        mods_result = await db.execute(
            select(AgencyModule).where(
                AgencyModule.agency_id == agency.id,
                AgencyModule.is_active.is_(True),
            )
        )
        active_modules = [m.module_code for m in mods_result.scalars().all()]

        summaries.append(AgencySummary(
            id=agency.id,
            name=agency.name,
            owner_email=agency.owner_email,
            status=agency.status,
            plan_tier=agency.plan_tier,
            active_modules=active_modules,
            created_at=agency.created_at,
        ))

    return summaries