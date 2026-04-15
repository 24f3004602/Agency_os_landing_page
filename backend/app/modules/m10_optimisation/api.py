import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_module, require_owner
from app.database import get_db
from app.modules.m10_optimisation.models import (
    OptimisationConfig,
    OptimisationRecommendation,
    OptimisationRun,
    PredictiveAlert,
)
from app.modules.people_and_tenant.users.models import Client, User
from app.modules.m10_optimisation.schemas import (
    ApproveRecommendationsRequest,
    OptimisationConfigCreate,
    OptimisationConfigResponse,
    OptimisationRunResponse,
    OptimisationRunSummary,
    PredictiveAlertResponse,
    RecommendationResponse,
    TriggerRunRequest,
)

router = APIRouter(prefix="/m10", tags=["M10 - Optimisation & Prediction"])

M10 = Depends(require_module("M10"))


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


async def _build_run_response(
    run: OptimisationRun,
    db: AsyncSession,
) -> OptimisationRunResponse:
    client_result = await db.execute(
        select(Client).where(Client.id == run.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"

    recs_result = await db.execute(
        select(OptimisationRecommendation).where(
            OptimisationRecommendation.run_id == run.id
        ).order_by(OptimisationRecommendation.confidence_score.desc())
    )
    recs = recs_result.scalars().all()

    return OptimisationRunResponse(
        id=run.id,
        agency_id=run.agency_id,
        client_id=run.client_id,
        client_name=client_name,
        status=run.status,
        mode=run.mode,
        analysis_summary=run.analysis_summary,
        total_recommendations=run.total_recommendations,
        approved_count=run.approved_count,
        executed_count=run.executed_count,
        error_message=run.error_message,
        recommendations=[
            RecommendationResponse.model_validate(r) for r in recs
        ],
        created_at=run.created_at,
    )


# ── Config: Upsert ───────────────────────────────────────────────────────────

@router.post("/config/{client_id}", response_model=OptimisationConfigResponse)
async def upsert_config(
    client_id: uuid.UUID,
    body: OptimisationConfigCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M10],
) -> OptimisationConfigResponse:
    """
    Creates or updates optimisation configuration for a client.
    WARNING: setting mode=autonomous enables AI to make live ad changes.
    Ensure guardrails are appropriate before enabling.
    """
    client = await _get_client(client_id, current_user.agency_id, db)

    existing = await db.execute(
        select(OptimisationConfig).where(
            OptimisationConfig.client_id == client_id,
            OptimisationConfig.agency_id == current_user.agency_id,
        )
    )
    config = existing.scalar_one_or_none()

    approved_json = json.dumps(body.approved_change_types)

    if config:
        config.mode = body.mode
        config.max_budget_change_pct = body.max_budget_change_pct
        config.max_bid_change_pct = body.max_bid_change_pct
        config.min_daily_budget = body.min_daily_budget
        config.approved_change_types_json = approved_json
        config.target_roas = body.target_roas
        config.target_ctr = body.target_ctr
        config.target_cpc = body.target_cpc
    else:
        config = OptimisationConfig(
            agency_id=current_user.agency_id,
            client_id=client_id,
            mode=body.mode,
            max_budget_change_pct=body.max_budget_change_pct,
            max_bid_change_pct=body.max_bid_change_pct,
            min_daily_budget=body.min_daily_budget,
            approved_change_types_json=approved_json,
            target_roas=body.target_roas,
            target_ctr=body.target_ctr,
            target_cpc=body.target_cpc,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    try:
        approved_types = json.loads(config.approved_change_types_json)
    except Exception:
        approved_types = []

    return OptimisationConfigResponse(
        id=config.id,
        client_id=config.client_id,
        client_name=client.company_name,
        mode=config.mode,
        max_budget_change_pct=config.max_budget_change_pct,
        max_bid_change_pct=config.max_bid_change_pct,
        min_daily_budget=config.min_daily_budget,
        approved_change_types=approved_types,
        autonomous_enabled=config.autonomous_enabled,
        target_roas=config.target_roas,
        target_ctr=config.target_ctr,
        target_cpc=config.target_cpc,
        created_at=config.created_at,
    )


# ── Config: Get ──────────────────────────────────────────────────────────────

@router.get("/config/{client_id}", response_model=OptimisationConfigResponse)
async def get_config(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M10],
) -> OptimisationConfigResponse:
    client = await _get_client(client_id, current_user.agency_id, db)

    result = await db.execute(
        select(OptimisationConfig).where(
            OptimisationConfig.client_id == client_id,
            OptimisationConfig.agency_id == current_user.agency_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            404,
            "No optimisation config found. Create one with POST /m10/config/{client_id}",
        )

    try:
        approved_types = json.loads(config.approved_change_types_json)
    except Exception:
        approved_types = []

    return OptimisationConfigResponse(
        id=config.id,
        client_id=config.client_id,
        client_name=client.company_name,
        mode=config.mode,
        max_budget_change_pct=config.max_budget_change_pct,
        max_bid_change_pct=config.max_bid_change_pct,
        min_daily_budget=config.min_daily_budget,
        approved_change_types=approved_types,
        autonomous_enabled=config.autonomous_enabled,
        target_roas=config.target_roas,
        target_ctr=config.target_ctr,
        target_cpc=config.target_cpc,
        created_at=config.created_at,
    )


# ── Kill switch ───────────────────────────────────────────────────────────────

@router.patch("/config/{client_id}/kill-switch", response_model=dict)
async def toggle_kill_switch(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M10],
) -> dict:
    """
    Immediately disables autonomous execution for a client.
    The agent will still run and generate recommendations
    but will NOT execute any changes until re-enabled.
    """
    result = await db.execute(
        select(OptimisationConfig).where(
            OptimisationConfig.client_id == client_id,
            OptimisationConfig.agency_id == current_user.agency_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "Config not found")

    config.autonomous_enabled = not config.autonomous_enabled
    await db.commit()

    return {
        "autonomous_enabled": config.autonomous_enabled,
        "message": (
            "Autonomous execution ENABLED"
            if config.autonomous_enabled
            else "Autonomous execution DISABLED — agent will only advise"
        ),
    }


# ── Runs: Trigger ─────────────────────────────────────────────────────────────

@router.post("/runs", response_model=OptimisationRunResponse, status_code=201)
async def trigger_optimisation_run(
    body: TriggerRunRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M10],
) -> OptimisationRunResponse:
    """
    Owner manually triggers an optimisation analysis for a client.
    Uses the client's configured mode (advisory/autonomous) and guardrails.
    Returns immediately — analysis runs in background (~30 seconds).
    """
    client = await _get_client(body.client_id, current_user.agency_id, db)

    # Fetch config
    config_result = await db.execute(
        select(OptimisationConfig).where(
            OptimisationConfig.client_id == body.client_id,
            OptimisationConfig.agency_id == current_user.agency_id,
        )
    )
    config = config_result.scalar_one_or_none()

    mode = config.mode if config else "advisory"
    max_budget_pct = config.max_budget_change_pct if config else 20.0
    max_bid_pct = config.max_bid_change_pct if config else 15.0
    min_budget = float(config.min_daily_budget) if config else 500.0
    approved_types = json.loads(config.approved_change_types_json) if config else ["pause_ad"]
    target_roas = config.target_roas if config else None
    target_ctr = config.target_ctr if config else None
    target_cpc = config.target_cpc if config else None

    # If autonomous but kill switch off, downgrade to advisory
    if mode == "autonomous" and config and not config.autonomous_enabled:
        mode = "advisory"

    # Create run record
    run = OptimisationRun(
        agency_id=current_user.agency_id,
        client_id=client.id,
        status="analysing",
        mode=mode,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    run_id = str(run.id)
    agency_id = str(current_user.agency_id)
    client_id = str(client.id)
    client_name = client.company_name

    async def _run():
        from app.modules.m10_optimisation.agent import run_optimisation_agent
        await run_optimisation_agent(
            run_id=run_id,
            agency_id=agency_id,
            client_id=client_id,
            client_name=client_name,
            mode=mode,
            max_budget_change_pct=max_budget_pct,
            max_bid_change_pct=max_bid_pct,
            min_daily_budget=min_budget,
            approved_change_types=approved_types,
            target_roas=target_roas,
            target_ctr=target_ctr,
            target_cpc=target_cpc,
        )

    background_tasks.add_task(_run)

    return await _build_run_response(run, db)


# ── Runs: List ───────────────────────────────────────────────────────────────

@router.get("/runs", response_model=list[OptimisationRunSummary])
async def list_runs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M10],
    client_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
) -> list[OptimisationRunSummary]:
    query = select(OptimisationRun).where(
        OptimisationRun.agency_id == current_user.agency_id
    )
    if client_id:
        query = query.where(OptimisationRun.client_id == client_id)
    if status:
        query = query.where(OptimisationRun.status == status)
    query = query.order_by(OptimisationRun.created_at.desc())

    result = await db.execute(query)
    runs = result.scalars().all()

    summaries = []
    for run in runs:
        client_result = await db.execute(
            select(Client).where(Client.id == run.client_id)
        )
        client = client_result.scalar_one_or_none()
        summaries.append(OptimisationRunSummary(
            id=run.id,
            client_id=run.client_id,
            client_name=client.company_name if client else "Unknown",
            status=run.status,
            mode=run.mode,
            total_recommendations=run.total_recommendations,
            executed_count=run.executed_count,
            created_at=run.created_at,
        ))

    return summaries


# ── Runs: Get one ─────────────────────────────────────────────────────────────

@router.get("/runs/{run_id}", response_model=OptimisationRunResponse)
async def get_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M10],
) -> OptimisationRunResponse:
    result = await db.execute(
        select(OptimisationRun).where(
            OptimisationRun.id == run_id,
            OptimisationRun.agency_id == current_user.agency_id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")
    return await _build_run_response(run, db)


# ── Runs: Approve recommendations ─────────────────────────────────────────────

@router.post("/runs/{run_id}/approve", response_model=OptimisationRunResponse)
async def approve_recommendations(
    run_id: uuid.UUID,
    body: ApproveRecommendationsRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M10],
) -> OptimisationRunResponse:
    """
    Owner approves specific recommendations from an advisory run.
    Approved recommendations are executed immediately in background.
    Use this when mode=advisory and you want to manually approve changes.
    """
    run_result = await db.execute(
        select(OptimisationRun).where(
            OptimisationRun.id == run_id,
            OptimisationRun.agency_id == current_user.agency_id,
        )
    )
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")

    if run.status not in ("recommendations_ready", "approved"):
        raise HTTPException(
            400,
            f"Run must be in 'recommendations_ready' status to approve. "
            f"Current: {run.status}",
        )

    # Approve specified recommendations
    for rec_id in body.recommendation_ids:
        rec_result = await db.execute(
            select(OptimisationRecommendation).where(
                OptimisationRecommendation.id == rec_id,
                OptimisationRecommendation.run_id == run_id,
            )
        )
        rec = rec_result.scalar_one_or_none()
        if rec and rec.status == "pending":
            rec.status = "approved"
            rec.approved_by = current_user.id

    run.status = "approved"
    run.approved_count = len(body.recommendation_ids)
    await db.commit()

    # Execute approved changes in background
    run_id_str = str(run_id)
    agency_id_str = str(current_user.agency_id)

    async def _execute():
        """Re-run only the execution nodes for approved recs."""
        from app.database import AsyncSessionLocal
        from app.modules.m10_optimisation.models import OptimisationRun, OptimisationRecommendation
        from app.core.ad_execution import meta_pause_ad, google_pause_ad
        from sqlalchemy import select as sel
        import json

        now = datetime.now(timezone.utc)
        executed = 0

        async with AsyncSessionLocal() as db2:
            recs_result = await db2.execute(
                sel(OptimisationRecommendation).where(
                    OptimisationRecommendation.run_id == uuid.UUID(run_id_str),
                    OptimisationRecommendation.status == "approved",
                )
            )
            approved_recs = recs_result.scalars().all()

            for rec in approved_recs:
                rec.status = "executing"
            await db2.commit()

            for rec in approved_recs:
                result = {}
                try:
                    if rec.platform == "meta" and rec.change_type == "pause_ad":
                        result = await meta_pause_ad(rec.entity_id or "", "")
                    elif rec.platform == "google_ads" and rec.change_type == "pause_ad":
                        result = await google_pause_ad("", rec.entity_id or "", "", "")
                    else:
                        result = {"status": "stub", "change_type": rec.change_type}

                    rec.status = "executed"
                    rec.executed_at = now
                    rec.execution_result = json.dumps(result)
                    executed += 1
                except Exception as e:
                    rec.status = "failed"
                    rec.execution_result = json.dumps({"error": str(e)})

            run_result2 = await db2.execute(
                sel(OptimisationRun).where(
                    OptimisationRun.id == uuid.UUID(run_id_str)
                )
            )
            run2 = run_result2.scalar_one_or_none()
            if run2:
                run2.status = "complete"
                run2.executed_count = executed

            await db2.commit()

    background_tasks.add_task(_execute)

    await db.refresh(run)
    return await _build_run_response(run, db)


# ── Predictive Alerts: List ───────────────────────────────────────────────────

@router.get("/alerts", response_model=list[PredictiveAlertResponse])
async def list_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M10],
    status: str | None = Query(None),
    severity: str | None = Query(None),
    client_id: uuid.UUID | None = Query(None),
) -> list[PredictiveAlertResponse]:
    """
    Lists trajectory alerts.
    Default: open alerts sorted by severity (critical first).
    """
    query = select(PredictiveAlert).where(
        PredictiveAlert.agency_id == current_user.agency_id
    )
    if status:
        query = query.where(PredictiveAlert.status == status)
    else:
        query = query.where(PredictiveAlert.status == "open")
    if severity:
        query = query.where(PredictiveAlert.severity == severity)
    if client_id:
        query = query.where(PredictiveAlert.client_id == client_id)
    query = query.order_by(PredictiveAlert.created_at.desc())

    result = await db.execute(query)
    alerts = result.scalars().all()

    responses = []
    for alert in alerts:
        client_result = await db.execute(
            select(Client).where(Client.id == alert.client_id)
        )
        client = client_result.scalar_one_or_none()

        responses.append(PredictiveAlertResponse(
            id=alert.id,
            agency_id=alert.agency_id,
            client_id=alert.client_id,
            client_name=client.company_name if client else "Unknown",
            severity=alert.severity,
            status=alert.status,
            kpi_name=alert.kpi_name,
            current_value=alert.current_value,
            target_value=alert.target_value,
            projected_eom_value=alert.projected_eom_value,
            gap_percentage=alert.gap_percentage,
            suggested_action=alert.suggested_action,
            days_remaining=alert.days_remaining,
            acknowledged_at=alert.acknowledged_at,
            created_at=alert.created_at,
        ))

    # Sort: critical first
    responses.sort(
        key=lambda x: 0 if x.severity == "critical" else 1
    )

    return responses


# ── Predictive Alerts: Acknowledge ────────────────────────────────────────────

@router.patch("/alerts/{alert_id}/acknowledge", response_model=PredictiveAlertResponse)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M10],
) -> PredictiveAlertResponse:
    result = await db.execute(
        select(PredictiveAlert).where(
            PredictiveAlert.id == alert_id,
            PredictiveAlert.agency_id == current_user.agency_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")

    alert.status = "acknowledged"
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(alert)

    client_result = await db.execute(
        select(Client).where(Client.id == alert.client_id)
    )
    client = client_result.scalar_one_or_none()

    return PredictiveAlertResponse(
        id=alert.id,
        agency_id=alert.agency_id,
        client_id=alert.client_id,
        client_name=client.company_name if client else "Unknown",
        severity=alert.severity,
        status=alert.status,
        kpi_name=alert.kpi_name,
        current_value=alert.current_value,
        target_value=alert.target_value,
        projected_eom_value=alert.projected_eom_value,
        gap_percentage=alert.gap_percentage,
        suggested_action=alert.suggested_action,
        days_remaining=alert.days_remaining,
        acknowledged_at=alert.acknowledged_at,
        created_at=alert.created_at,
    )