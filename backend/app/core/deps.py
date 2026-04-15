import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.database import get_db
from app.modules.people_and_tenant.agencies.models import AgencyModule
from app.modules.people_and_tenant.users.models import User, UserRole

bearer = HTTPBearer()


# ─── Raw token → user dict ─────────────────────────────────────────────────────

async def get_current_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> dict:
    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cannot be used here",
        )
    return payload


# ─── Token → User row ─────────────────────────────────────────────────────────

async def get_current_user(
    payload: Annotated[dict, Depends(get_current_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    # SuperAdmin is not stored in DB — synthesise a virtual User object
    if payload.get("role") == UserRole.SUPERADMIN:
        virtual = User()
        virtual.id = uuid.UUID(payload["sub"])
        virtual.role = UserRole.SUPERADMIN
        virtual.agency_id = None
        return virtual

    result = await db.execute(select(User).where(User.id == uuid.UUID(payload["sub"])))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


# ─── Role guards ───────────────────────────────────────────────────────────────

def require_role(*roles: str):
    """Returns a dependency that enforces one of the given roles."""

    async def _guard(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(roles)}",
            )
        return current_user

    return _guard


require_superadmin = require_role(UserRole.SUPERADMIN)
require_owner = require_role(UserRole.SUPERADMIN, UserRole.OWNER)
require_employee = require_role(UserRole.SUPERADMIN, UserRole.OWNER, UserRole.EMPLOYEE)
require_any = require_role(
    UserRole.SUPERADMIN, UserRole.OWNER, UserRole.EMPLOYEE, UserRole.CLIENT
)


# ─── Module guard ──────────────────────────────────────────────────────────────

def require_module(module_code: str):
    """
    Dependency that checks whether the current user's agency has the given
    module active. SuperAdmin bypasses this check.
    """

    async def _guard(
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        if current_user.role == UserRole.SUPERADMIN:
            return current_user

        result = await db.execute(
            select(AgencyModule).where(
                AgencyModule.agency_id == current_user.agency_id,
                AgencyModule.module_code == module_code,
                AgencyModule.is_active.is_(True),
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module {module_code} is not active for your agency",
            )
        return current_user

    return _guard
