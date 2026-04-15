import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.core.security import (
    build_token_payload,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.database import get_db
from app.modules.people_and_tenant.agencies.models import AgencyModule, MODULES
from app.modules.people_and_tenant.users.models import User, UserRole
from app.modules.people_and_tenant.auth.schemas import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# Stable UUID for SuperAdmin — derived from email so it never changes
SUPERADMIN_UUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, settings.superadmin_email))


async def _active_modules_for_agency(
    db: AsyncSession,
    agency_id: uuid.UUID | None,
) -> list[str]:
    if not agency_id:
        return []

    result = await db.execute(
        select(AgencyModule.module_code).where(
            AgencyModule.agency_id == agency_id,
            AgencyModule.is_active.is_(True),
        )
    )
    return sorted(result.scalars().all())


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    # ── 1. SuperAdmin check (env-var credentials, not in DB) ──────────────────
    if body.email.lower() == settings.superadmin_email.lower():
        if body.password != settings.superadmin_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        payload = build_token_payload(
            user_id=SUPERADMIN_UUID,
            role=UserRole.SUPERADMIN,
        )
        return TokenResponse(
            access_token=create_access_token(payload),
            refresh_token=create_refresh_token(payload),
            role=UserRole.SUPERADMIN,
            user_id=SUPERADMIN_UUID,
            agency_id=None,
            full_name="Super Admin",
            active_modules=sorted(MODULES.keys()),
        )

    # ── 2. Regular user (owner / employee / client) ───────────────────────────
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # Update last_login
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    payload = build_token_payload(
        user_id=str(user.id),
        role=user.role,
        agency_id=str(user.agency_id) if user.agency_id else None,
    )

    active_modules = await _active_modules_for_agency(db, user.agency_id)

    return TokenResponse(
        access_token=create_access_token(payload),
        refresh_token=create_refresh_token(payload),
        role=user.role,
        user_id=str(user.id),
        agency_id=str(user.agency_id) if user.agency_id else None,
        full_name=user.full_name,
        active_modules=active_modules,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a refresh token",
        )

    role = payload["role"]
    user_id = payload["sub"]
    agency_id = payload.get("agency_id")
    full_name = "Super Admin"

    if role != UserRole.SUPERADMIN:
        result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        full_name = user.full_name

    active_modules = (
        sorted(MODULES.keys())
        if role == UserRole.SUPERADMIN
        else await _active_modules_for_agency(
            db,
            uuid.UUID(agency_id) if agency_id else None,
        )
    )

    new_payload = build_token_payload(user_id=user_id, role=role, agency_id=agency_id)

    return TokenResponse(
        access_token=create_access_token(new_payload),
        refresh_token=create_refresh_token(new_payload),
        role=role,
        user_id=user_id,
        agency_id=agency_id,
        full_name=full_name,
        active_modules=active_modules,
    )


@router.get("/me")
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Returns current user context including active agency modules."""
    if current_user.role == UserRole.SUPERADMIN:
        return {
            "status": "ok",
            "role": UserRole.SUPERADMIN,
            "user_id": str(current_user.id),
            "agency_id": None,
            "full_name": "Super Admin",
            "active_modules": sorted(MODULES.keys()),
        }

    active_modules = await _active_modules_for_agency(db, current_user.agency_id)
    return {
        "status": "ok",
        "role": current_user.role,
        "user_id": str(current_user.id),
        "agency_id": str(current_user.agency_id) if current_user.agency_id else None,
        "full_name": current_user.full_name,
        "active_modules": active_modules,
    }
