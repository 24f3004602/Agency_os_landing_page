import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_owner
from app.database import get_db
from app.modules.people_and_tenant.users.models import Client, Employee, User
from app.modules.people_and_tenant.clients.schemas import ClientCreate, ClientResponse, ClientUpdate

router = APIRouter(prefix="/clients", tags=["clients"])


# ── Helper ───────────────────────────────────────────────────────────────────

async def _build_response(client: Client, db: AsyncSession) -> ClientResponse:
    account_manager_name = None
    if client.account_manager_id:
        emp_result = await db.execute(
            select(Employee).where(Employee.id == client.account_manager_id)
        )
        emp = emp_result.scalar_one_or_none()
        if emp:
            user_result = await db.execute(
                select(User).where(User.id == emp.user_id)
            )
            user = user_result.scalar_one_or_none()
            account_manager_name = user.full_name if user else None

    return ClientResponse(
        id=client.id,
        agency_id=client.agency_id,
        company_name=client.company_name,
        contact_name=client.contact_name,
        contact_email=client.contact_email,
        contact_phone=client.contact_phone,
        status=client.status,
        account_manager_id=client.account_manager_id,
        account_manager_name=account_manager_name,
        hubspot_deal_id=client.hubspot_deal_id,
        notes=client.notes,
        has_portal_access=client.user_id is not None,
        created_at=client.created_at,
        updated_at=client.updated_at,
    )


# ── Create ───────────────────────────────────────────────────────────────────

@router.post("", response_model=ClientResponse, status_code=201)
async def create_client(
    body: ClientCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> ClientResponse:
    # If account manager specified, verify they belong to this agency
    if body.account_manager_id:
        emp_result = await db.execute(
            select(Employee).where(
                Employee.id == body.account_manager_id,
                Employee.agency_id == current_user.agency_id,
            )
        )
        if not emp_result.scalar_one_or_none():
            raise HTTPException(404, "Account manager not found in your agency")

    client = Client(
        agency_id=current_user.agency_id,
        company_name=body.company_name,
        contact_name=body.contact_name,
        contact_email=body.contact_email.lower(),
        contact_phone=body.contact_phone,
        account_manager_id=body.account_manager_id,
        hubspot_deal_id=body.hubspot_deal_id,
        notes=body.notes,
        status="active",
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return await _build_response(client, db)


# ── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ClientResponse])
async def list_clients(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
    status: str | None = Query(None),
    account_manager_id: uuid.UUID | None = Query(None),
) -> list[ClientResponse]:
    query = select(Client).where(
        Client.agency_id == current_user.agency_id
    )
    if status:
        query = query.where(Client.status == status)
    if account_manager_id:
        query = query.where(Client.account_manager_id == account_manager_id)

    query = query.order_by(Client.created_at.desc())
    result = await db.execute(query)
    clients = result.scalars().all()

    return [await _build_response(c, db) for c in clients]


# ── Get one ──────────────────────────────────────────────────────────────────

@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> ClientResponse:
    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.agency_id == current_user.agency_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Client not found")

    return await _build_response(client, db)


# ── Update ───────────────────────────────────────────────────────────────────

@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: uuid.UUID,
    body: ClientUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> ClientResponse:
    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.agency_id == current_user.agency_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Client not found")

    # Validate new account manager belongs to agency
    update_data = body.model_dump(exclude_unset=True)
    if "account_manager_id" in update_data and update_data["account_manager_id"]:
        emp_result = await db.execute(
            select(Employee).where(
                Employee.id == update_data["account_manager_id"],
                Employee.agency_id == current_user.agency_id,
            )
        )
        if not emp_result.scalar_one_or_none():
            raise HTTPException(404, "Account manager not found in your agency")

    for field, value in update_data.items():
        setattr(client, field, value)

    await db.commit()
    await db.refresh(client)
    return await _build_response(client, db)


# ── Soft delete ──────────────────────────────────────────────────────────────

@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> None:
    """Marks client as churned — data preserved."""
    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.agency_id == current_user.agency_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(404, "Client not found")

    client.status = "churned"
    await db.commit()