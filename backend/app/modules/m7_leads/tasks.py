"""
M7 Celery Tasks — Lead Analyst Agent

Tasks:
  - score_unscored_leads : runs every hour
                           finds leads with status=new and runs
                           the LeadScoringAgent on each
"""
import asyncio
import logging

from celery_worker import celery_app
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.m7_tasks.score_unscored_leads", bind=True)
def score_unscored_leads(self):
    """
    Runs every hour.
    Finds all leads with status='new' across all M7-enabled agencies
    and runs the LeadScoringAgent on each.
    """
    logger.info("Starting unscored leads scan")
    run_async(_score_unscored_leads_async())
    logger.info("Unscored leads scan complete")


async def _score_unscored_leads_async() -> None:
    from sqlalchemy import select
    from app.modules.people_and_tenant.agencies.models import AgencyModule
    from app.modules.m7_leads.models import Lead
    from app.modules.m7_leads.agent import run_lead_agent

    async with AsyncSessionLocal() as db:
        m7_result = await db.execute(
            select(AgencyModule).where(
                AgencyModule.module_code == "M7",
                AgencyModule.is_active.is_(True),
            )
        )
        m7_modules = m7_result.scalars().all()

    if not m7_modules:
        logger.info("No agencies have M7 active — skipping")
        return

    active_agency_ids = [m.agency_id for m in m7_modules]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Lead).where(
                Lead.status == "new",
                Lead.agency_id.in_(active_agency_ids),
            )
        )
        unscored = result.scalars().all()

    if not unscored:
        logger.info("No unscored leads found")
        return

    logger.info("Scoring %d unscored lead(s)", len(unscored))

    for lead in unscored:
        try:
            await run_lead_agent(
                lead_id=str(lead.id),
                agency_id=str(lead.agency_id),
            )
        except Exception as e:
            logger.error(
                "Lead scoring failed for %s: %s",
                lead.company_name,
                e,
            )