"""
M4 Celery Tasks — Churn Prevention Agent

Tasks:
  - run_churn_scan : daily at 07:00 IST
                     evaluates every active client in every M4-enabled agency
                     runs the ChurnRiskAgent for each
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from celery_worker import celery_app
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.m4_tasks.run_churn_scan", bind=True)
def run_churn_scan(self):
    """
    Daily churn scan — 07:00 IST = 01:30 UTC.
    Runs churn agent for every active client in every
    agency that has M4 active.
    """
    logger.info("Starting daily churn scan")
    run_async(_run_churn_scan_async())
    logger.info("Churn scan complete")


async def _run_churn_scan_async() -> None:
    from app.modules.people_and_tenant.agencies.models import Agency, AgencyModule
    from app.modules.people_and_tenant.users.models import Client
    from app.modules.m4_churn.agent import run_churn_agent

    async with AsyncSessionLocal() as db:
        # Find all agencies with M4 active
        m4_result = await db.execute(
            select(AgencyModule).where(
                AgencyModule.module_code == "M4",
                AgencyModule.is_active.is_(True),
            )
        )
        m4_modules = m4_result.scalars().all()

        if not m4_modules:
            logger.info("No agencies have M4 active — skipping churn scan")
            return

        logger.info("Running churn scan for %d agency/agencies", len(m4_modules))

        for module in m4_modules:
            # Check if M6 is also active for this agency (enrichment)
            m6_result = await db.execute(
                select(AgencyModule).where(
                    AgencyModule.agency_id == module.agency_id,
                    AgencyModule.module_code == "M6",
                    AgencyModule.is_active.is_(True),
                )
            )
            is_m6_active = m6_result.scalar_one_or_none() is not None

            # Get all active clients for this agency
            clients_result = await db.execute(
                select(Client).where(
                    Client.agency_id == module.agency_id,
                    Client.status.in_(["active", "at_risk"]),
                )
            )
            clients = clients_result.scalars().all()

            logger.info(
                "Agency %s: scanning %d client(s)",
                module.agency_id,
                len(clients),
            )

            for client in clients:
                try:
                    await run_churn_agent(
                        client_id=str(client.id),
                        client_name=client.company_name,
                        agency_id=str(module.agency_id),
                        is_m6_active=is_m6_active,
                    )
                except Exception as e:
                    logger.error(
                        "Churn agent failed for client %s: %s",
                        client.company_name,
                        e,
                    )
                    continue