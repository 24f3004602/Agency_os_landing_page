import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_module, require_owner
from app.database import get_db
from app.modules.m4_churn.models import ChurnAlert
from app.modules.people_and_tenant.users.models import Client, User
from app.modules.m4_churn.schemas import (
    ChurnAlertResponse,
    ClientRiskScore,
    ResolveAlertRequest,
)

router = APIRouter(prefix="/m4", tags=["M4 - Churn Prevention"])

M4 = Depends(require_module("M4"))


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _build_alert_response(
    alert: ChurnAlert,
    db: AsyncSession,
) -> ChurnAlertResponse:
    import json

    client_result = await db.execute(
        select(Client).where(Client.id == alert.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"
    client_status = client.status if client else "unknown"

    try:
        trigger_reasons = json.loads(alert.trigger_reasons_json)
    except Exception:
        trigger_reasons = []

    try:
        retention_actions = json.loads(alert.retention_actions_json)
    except Exception:
        retention_actions = []

    return ChurnAlertResponse(
        id=alert.id,
        agency_id=alert.agency_id,
        client_id=alert.client_id,
        client_name=client_name,
        client_status=client_status,
        risk_score=alert.risk_score,
        trigger_reasons=trigger_reasons,
        retention_actions=retention_actions,
        competitor_context=alert.competitor_context,
        status=alert.status,
        resolved_at=alert.resolved_at,
        resolution_note=alert.resolution_note,
        created_at=alert.created_at,
    )


# ── List alerts ──────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=list[ChurnAlertResponse])
async def list_churn_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M4],
    status: str | None = Query(None),             # open | resolved | false_positive
    min_score: float | None = Query(None, ge=0, le=100),
    client_id: uuid.UUID | None = Query(None),
) -> list[ChurnAlertResponse]:
    """
    Lists churn alerts for the agency.
    Defaults to open alerts sorted by risk score descending
    (highest risk first).
    """
    query = select(ChurnAlert).where(
        ChurnAlert.agency_id == current_user.agency_id
    )

    if status:
        query = query.where(ChurnAlert.status == status)
    else:
        # Default: only open alerts
        query = query.where(ChurnAlert.status == "open")

    if min_score is not None:
        query = query.where(ChurnAlert.risk_score >= min_score)

    if client_id:
        query = query.where(ChurnAlert.client_id == client_id)

    query = query.order_by(ChurnAlert.risk_score.desc())

    result = await db.execute(query)
    alerts = result.scalars().all()

    return [await _build_alert_response(a, db) for a in alerts]


# ── Get single alert ─────────────────────────────────────────────────────────

@router.get("/alerts/{alert_id}", response_model=ChurnAlertResponse)
async def get_churn_alert(
    alert_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M4],
) -> ChurnAlertResponse:
    result = await db.execute(
        select(ChurnAlert).where(
            ChurnAlert.id == alert_id,
            ChurnAlert.agency_id == current_user.agency_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")

    return await _build_alert_response(alert, db)


# ── Resolve alert ────────────────────────────────────────────────────────────

@router.patch("/alerts/{alert_id}/resolve", response_model=ChurnAlertResponse)
async def resolve_churn_alert(
    alert_id: uuid.UUID,
    body: ResolveAlertRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M4],
) -> ChurnAlertResponse:
    """
    Owner marks an alert as resolved or false positive.
    If resolved: client status reverts to active.
    """
    if body.resolution not in ("resolved", "false_positive"):
        raise HTTPException(
            400,
            "resolution must be 'resolved' or 'false_positive'"
        )

    result = await db.execute(
        select(ChurnAlert).where(
            ChurnAlert.id == alert_id,
            ChurnAlert.agency_id == current_user.agency_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")

    if alert.status != "open":
        raise HTTPException(
            409,
            f"Alert is already {alert.status}"
        )

    alert.status = body.resolution
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = current_user.id
    alert.resolution_note = body.note

    # If resolved or false positive, check if client
    # has any other open alerts — if not, revert to active
    other_open = await db.execute(
        select(func.count(ChurnAlert.id)).where(
            ChurnAlert.client_id == alert.client_id,
            ChurnAlert.status == "open",
            ChurnAlert.id != alert_id,
        )
    )
    other_open_count = other_open.scalar() or 0

    if other_open_count == 0:
        client_result = await db.execute(
            select(Client).where(Client.id == alert.client_id)
        )
        client = client_result.scalar_one_or_none()
        if client and client.status == "at_risk":
            client.status = "active"

    await db.commit()
    await db.refresh(alert)
    return await _build_alert_response(alert, db)


# ── Risk scores for all clients ──────────────────────────────────────────────

@router.get("/risk-scores", response_model=list[ClientRiskScore])
async def get_all_risk_scores(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M4],
) -> list[ClientRiskScore]:
    """
    Returns current risk snapshot for every active client.
    Shows latest risk score and open alert count per client.
    Sorted highest risk first.
    """
    clients_result = await db.execute(
        select(Client).where(
            Client.agency_id == current_user.agency_id,
            Client.status.in_(["active", "at_risk"]),
        ).order_by(Client.company_name)
    )
    clients = clients_result.scalars().all()

    scores = []
    for client in clients:
        # Latest alert
        latest_alert_result = await db.execute(
            select(ChurnAlert).where(
                ChurnAlert.client_id == client.id,
            ).order_by(ChurnAlert.created_at.desc()).limit(1)
        )
        latest_alert = latest_alert_result.scalar_one_or_none()

        # Count open alerts
        open_count_result = await db.execute(
            select(func.count(ChurnAlert.id)).where(
                ChurnAlert.client_id == client.id,
                ChurnAlert.status == "open",
            )
        )
        open_count = open_count_result.scalar() or 0

        scores.append(ClientRiskScore(
            client_id=client.id,
            client_name=client.company_name,
            client_status=client.status,
            risk_score=latest_alert.risk_score if latest_alert else None,
            last_alert_at=latest_alert.created_at if latest_alert else None,
            open_alerts=open_count,
        ))

    # Sort by risk score descending (None scores go last)
    scores.sort(
        key=lambda x: x.risk_score if x.risk_score is not None else -1,
        reverse=True,
    )

    return scores


# ── Manual scan trigger ──────────────────────────────────────────────────────

@router.post("/scan", status_code=202)
async def trigger_churn_scan(
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M4],
    client_id: uuid.UUID | None = Query(
        None,
        description="Scan a specific client only. Omit to scan all clients."
    ),
) -> dict:
    """
    Owner manually triggers churn scan without waiting for the
    daily Celery schedule.
    Returns 202 immediately — scan runs in background.
    Check GET /m4/alerts after a minute to see results.
    """
    from app.modules.m4_churn.agent import run_churn_agent
    from app.modules.people_and_tenant.agencies.models import AgencyModule
    from sqlalchemy import select

    # Check if M6 is active for enrichment
    m6_result = await db.execute(
        select(AgencyModule).where(
            AgencyModule.agency_id == current_user.agency_id,
            AgencyModule.module_code == "M6",
            AgencyModule.is_active.is_(True),
        )
    )
    is_m6_active = m6_result.scalar_one_or_none() is not None

    if client_id:
        # Scan specific client
        client_result = await db.execute(
            select(Client).where(
                Client.id == client_id,
                Client.agency_id == current_user.agency_id,
            )
        )
        client = client_result.scalar_one_or_none()
        if not client:
            raise HTTPException(404, "Client not found")

        async def _run_one():
            await run_churn_agent(
                client_id=str(client.id),
                client_name=client.company_name,
                agency_id=str(current_user.agency_id),
                is_m6_active=is_m6_active,
            )

        background_tasks.add_task(_run_one)
        return {
            "status": "scan_started",
            "scope": "single_client",
            "client": client.company_name,
            "message": "Scan running in background. Check /m4/alerts in ~30 seconds.",
        }

    else:
        # Scan all clients
        clients_result = await db.execute(
            select(Client).where(
                Client.agency_id == current_user.agency_id,
                Client.status.in_(["active", "at_risk"]),
            )
        )
        clients = clients_result.scalars().all()

        async def _run_all():
            for client in clients:
                try:
                    await run_churn_agent(
                        client_id=str(client.id),
                        client_name=client.company_name,
                        agency_id=str(current_user.agency_id),
                        is_m6_active=is_m6_active,
                    )
                except Exception as e:
                    logger.error(
                        "Scan failed for %s: %s",
                        client.company_name,
                        e,
                    )

        background_tasks.add_task(_run_all)
        return {
            "status": "scan_started",
            "scope": "all_clients",
            "client_count": len(clients),
            "message": f"Scanning {len(clients)} client(s). Check /m4/alerts in ~1 minute.",
        }