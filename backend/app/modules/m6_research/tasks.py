"""
M6 Celery Tasks — Research Agent

Tasks:
  - run_research_scan : weekly on Monday 06:00 IST = 00:30 UTC
                        runs ResearchAgent for every tracked competitor
                        in every M6-enabled agency
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


@celery_app.task(name="app.tasks.m6_tasks.run_research_scan", bind=True)
def run_research_scan(self):
    """
    Weekly research scan — Monday 06:00 IST = 00:30 UTC.
    Generates competitive intelligence briefs for all
    tracked competitors in all M6-active agencies.
    """
    logger.info("Starting weekly research scan")
    run_async(_run_research_scan_async())
    logger.info("Research scan complete")


async def _run_research_scan_async() -> None:
    from sqlalchemy import select
    from app.modules.people_and_tenant.agencies.models import AgencyModule
    from app.modules.m6_research.models import TrackedCompetitor, ResearchBrief
    from app.modules.people_and_tenant.users.models import Client
    from app.modules.m6_research.agent import run_research_agent

    async with AsyncSessionLocal() as db:
        m6_result = await db.execute(
            select(AgencyModule).where(
                AgencyModule.module_code == "M6",
                AgencyModule.is_active.is_(True),
            )
        )
        m6_modules = m6_result.scalars().all()

    if not m6_modules:
        logger.info("No agencies have M6 active — skipping research scan")
        return

    logger.info(
        "Running research scan for %d agency/agencies",
        len(m6_modules),
    )

    for module in m6_modules:
        async with AsyncSessionLocal() as db:
            # Get all active tracked competitors for this agency
            competitors_result = await db.execute(
                select(TrackedCompetitor).where(
                    TrackedCompetitor.agency_id == module.agency_id,
                    TrackedCompetitor.is_active.is_(True),
                )
            )
            competitors = competitors_result.scalars().all()

        if not competitors:
            logger.info(
                "Agency %s has no tracked competitors — skipping",
                module.agency_id,
            )
            continue

        logger.info(
            "Agency %s: researching %d competitor(s)",
            module.agency_id,
            len(competitors),
        )

        for competitor in competitors:
            # Fetch client name
            async with AsyncSessionLocal() as db:
                client_result = await db.execute(
                    select(Client).where(Client.id == competitor.client_id)
                )
                client = client_result.scalar_one_or_none()
                if not client:
                    continue
                client_name = client.company_name

                # Create brief record
                brief = ResearchBrief(
                    agency_id=module.agency_id,
                    client_id=competitor.client_id,
                    competitor_id=competitor.id,
                    competitor_name=competitor.competitor_name,
                )
                db.add(brief)
                await db.commit()
                await db.refresh(brief)
                brief_id = str(brief.id)

            try:
                await run_research_agent(
                    brief_id=brief_id,
                    agency_id=str(module.agency_id),
                    client_id=str(competitor.client_id),
                    client_name=client_name,
                    competitor_id=str(competitor.id),
                    competitor_name=competitor.competitor_name,
                    meta_page_id=competitor.meta_page_id,
                    domain=competitor.domain,
                    industry=competitor.industry,
                )
            except Exception as e:
                logger.error(
                    "Research agent failed for competitor %s: %s",
                    competitor.competitor_name,
                    e,
                )