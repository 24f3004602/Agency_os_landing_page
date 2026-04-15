"""
M10 Celery Tasks — Optimisation & Prediction Engine

Tasks:
  - run_daily_optimisation  : daily 10:00 IST = 04:30 UTC
                              analyses all active clients with M10
                              runs optimisation agent for each
  - run_trajectory_monitor  : daily 18:00 IST = 12:30 UTC
                              projects end-of-month performance
                              raises PredictiveAlert for at-risk KPIs
"""
import asyncio
import logging
from datetime import datetime, timezone

from celery_worker import celery_app
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.m10_tasks.run_daily_optimisation", bind=True)
def run_daily_optimisation(self):
    """Daily optimisation scan — 10:00 IST = 04:30 UTC."""
    logger.info("Starting daily optimisation scan")
    run_async(_run_daily_optimisation_async())
    logger.info("Daily optimisation scan complete")


async def _run_daily_optimisation_async() -> None:
    from sqlalchemy import select
    from app.modules.people_and_tenant.agencies.models import AgencyModule
    from app.modules.m10_optimisation.models import OptimisationConfig, OptimisationRun
    from app.modules.people_and_tenant.users.models import Client
    from app.modules.m10_optimisation.agent import run_optimisation_agent
    import json

    async with AsyncSessionLocal() as db:
        m10_result = await db.execute(
            select(AgencyModule).where(
                AgencyModule.module_code == "M10",
                AgencyModule.is_active.is_(True),
            )
        )
        m10_modules = m10_result.scalars().all()

    if not m10_modules:
        logger.info("No agencies have M10 active — skipping")
        return

    for module in m10_modules:
        async with AsyncSessionLocal() as db:
            # Get all configs for this agency
            configs_result = await db.execute(
                select(OptimisationConfig).where(
                    OptimisationConfig.agency_id == module.agency_id
                )
            )
            configs = configs_result.scalars().all()

        for config in configs:
            async with AsyncSessionLocal() as db:
                client_result = await db.execute(
                    select(Client).where(Client.id == config.client_id)
                )
                client = client_result.scalar_one_or_none()
                if not client or client.status not in ("active", "at_risk"):
                    continue

                # Create run record
                run = OptimisationRun(
                    agency_id=module.agency_id,
                    client_id=config.client_id,
                    status="analysing",
                    mode=config.mode,
                )
                db.add(run)
                await db.commit()
                await db.refresh(run)
                run_id = str(run.id)

            try:
                approved_types = json.loads(
                    config.approved_change_types_json
                )
            except Exception:
                approved_types = ["pause_ad"]

            try:
                await run_optimisation_agent(
                    run_id=run_id,
                    agency_id=str(module.agency_id),
                    client_id=str(config.client_id),
                    client_name=client.company_name,
                    mode=config.mode,
                    max_budget_change_pct=config.max_budget_change_pct,
                    max_bid_change_pct=config.max_bid_change_pct,
                    min_daily_budget=float(config.min_daily_budget),
                    approved_change_types=approved_types,
                    target_roas=config.target_roas,
                    target_ctr=config.target_ctr,
                    target_cpc=config.target_cpc,
                )
            except Exception as e:
                logger.error(
                    "Optimisation failed for client %s: %s",
                    client.company_name, e,
                )
                async with AsyncSessionLocal() as db:
                    from sqlalchemy import select as sel
                    run_result = await db.execute(
                        sel(OptimisationRun).where(
                            OptimisationRun.id == run.id
                        )
                    )
                    run_obj = run_result.scalar_one_or_none()
                    if run_obj:
                        run_obj.status = "failed"
                        run_obj.error_message = str(e)
                        await db.commit()


@celery_app.task(name="app.tasks.m10_tasks.run_trajectory_monitor", bind=True)
def run_trajectory_monitor(self):
    """Trajectory monitor — 18:00 IST = 12:30 UTC."""
    logger.info("Starting trajectory monitor")
    run_async(_run_trajectory_monitor_async())
    logger.info("Trajectory monitor complete")


async def _run_trajectory_monitor_async() -> None:
    from sqlalchemy import select
    from app.modules.people_and_tenant.agencies.models import AgencyModule
    from app.modules.m10_optimisation.models import OptimisationConfig, PredictiveAlert
    from app.modules.people_and_tenant.users.models import Client
    from app.modules.m10_optimisation.agent import run_trajectory_analysis

    async with AsyncSessionLocal() as db:
        m10_result = await db.execute(
            select(AgencyModule).where(
                AgencyModule.module_code == "M10",
                AgencyModule.is_active.is_(True),
            )
        )
        m10_modules = m10_result.scalars().all()

    for module in m10_modules:
        async with AsyncSessionLocal() as db:
            configs_result = await db.execute(
                select(OptimisationConfig).where(
                    OptimisationConfig.agency_id == module.agency_id
                )
            )
            configs = configs_result.scalars().all()

        for config in configs:
            async with AsyncSessionLocal() as db:
                client_result = await db.execute(
                    select(Client).where(Client.id == config.client_id)
                )
                client = client_result.scalar_one_or_none()
                if not client:
                    continue

            try:
                alert_data_list = await run_trajectory_analysis(
                    client_id=str(config.client_id),
                    agency_id=str(module.agency_id),
                    client_name=client.company_name,
                    target_roas=config.target_roas,
                    target_ctr=config.target_ctr,
                )

                for alert_data in alert_data_list:
                    async with AsyncSessionLocal() as db:
                        alert = PredictiveAlert(
                            agency_id=module.agency_id,
                            client_id=config.client_id,
                            severity=alert_data["severity"],
                            status="open",
                            kpi_name=alert_data["kpi_name"],
                            current_value=alert_data["current_value"],
                            target_value=alert_data["target_value"],
                            projected_eom_value=alert_data["projected_eom_value"],
                            gap_percentage=alert_data["gap_percentage"],
                            days_remaining=alert_data["days_remaining"],
                        )
                        db.add(alert)
                        await db.commit()

                    logger.warning(
                        "[SLACK STUB] ⚠️ Trajectory alert for %s — "
                        "%s projected at %s vs target %s (%s days remaining)",
                        client.company_name,
                        alert_data["kpi_name"].upper(),
                        alert_data["projected_eom_value"],
                        alert_data["target_value"],
                        alert_data["days_remaining"],
                    )

            except Exception as e:
                logger.error(
                    "Trajectory analysis failed for %s: %s",
                    client.company_name, e,
                )