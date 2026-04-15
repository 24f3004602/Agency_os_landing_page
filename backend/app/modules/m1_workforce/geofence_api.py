import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_owner
from app.database import get_db
from app.modules.m1_workforce.models_attendance import GeofenceZone
from app.modules.people_and_tenant.users.models import User
from app.modules.m1_workforce.schemas_attendance import (
    GeofenceZoneCreate,
    GeofenceZoneResponse,
    GeofenceZoneUpdate,
)

router = APIRouter(prefix="/geofence", tags=["geofence"])


@router.post("/zones", response_model=GeofenceZoneResponse, status_code=201)
async def create_zone(
    body: GeofenceZoneCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> GeofenceZoneResponse:
    """Create a new geofence zone for the agency. Owner only."""
    zone = GeofenceZone(
        agency_id=current_user.agency_id,
        name=body.name,
        latitude=body.latitude,
        longitude=body.longitude,
        radius_metres=body.radius_metres,
        notes=body.notes,
    )
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    return GeofenceZoneResponse.model_validate(zone)


@router.get("/zones", response_model=list[GeofenceZoneResponse])
async def list_zones(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
    include_inactive: bool = False,
) -> list[GeofenceZoneResponse]:
    """List all geofence zones for the agency."""
    query = select(GeofenceZone).where(
        GeofenceZone.agency_id == current_user.agency_id
    )
    if not include_inactive:
        query = query.where(GeofenceZone.is_active.is_(True))
    query = query.order_by(GeofenceZone.created_at.desc())

    result = await db.execute(query)
    zones = result.scalars().all()
    return [GeofenceZoneResponse.model_validate(z) for z in zones]


@router.get("/zones/{zone_id}", response_model=GeofenceZoneResponse)
async def get_zone(
    zone_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> GeofenceZoneResponse:
    """Get a specific geofence zone."""
    result = await db.execute(
        select(GeofenceZone).where(
            GeofenceZone.id == zone_id,
            GeofenceZone.agency_id == current_user.agency_id,
        )
    )
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return GeofenceZoneResponse.model_validate(zone)


@router.put("/zones/{zone_id}", response_model=GeofenceZoneResponse)
async def update_zone(
    zone_id: uuid.UUID,
    body: GeofenceZoneUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> GeofenceZoneResponse:
    """Update a geofence zone. Only provided fields are changed."""
    result = await db.execute(
        select(GeofenceZone).where(
            GeofenceZone.id == zone_id,
            GeofenceZone.agency_id == current_user.agency_id,
        )
    )
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(zone, field, value)

    await db.commit()
    await db.refresh(zone)
    return GeofenceZoneResponse.model_validate(zone)


@router.delete("/zones/{zone_id}", status_code=204)
async def delete_zone(
    zone_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> None:
    """
    Soft-delete a geofence zone by marking it inactive.
    Hard delete only if zone has no sessions linked to it.
    """
    result = await db.execute(
        select(GeofenceZone).where(
            GeofenceZone.id == zone_id,
            GeofenceZone.agency_id == current_user.agency_id,
        )
    )
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Soft delete — preserves historical session records
    zone.is_active = False
    await db.commit()
