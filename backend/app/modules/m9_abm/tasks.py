"""
M9 Celery Tasks — ABM Orchestrator

Tasks:
  - run_abm_weekly_review : every Monday 07:00 IST = 01:30 UTC
                            reviews all active ABM accounts
                            finds stale ones (7+ days no touch)
                            and runs the orchestration agent
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery_worker import celery_app
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.m9_tasks.run_abm_weekly_review", bind=True)
def run_abm_weekly_review(self):
    """
    Weekly ABM review — Monday 07:00 IST = 01:30 UTC.
    Finds stale accounts and orchestrates next touch.
    """
    logger.info("Starting ABM weekly review")
    run_async(_run_abm_weekly_review_async())
    logger.info("ABM weekly review complete")


async def _run_abm_weekly_review_async() -> None:
    from sqlalchemy import select
    from app.modules.people_and_tenant.agencies.models import AgencyModule
    from app.modules.m9_abm.models import AbmAccount
    from app.modules.m9_abm.agent import run_abm_agent

    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(days=7)

    async with AsyncSessionLocal() as db:
        # Find M9-enabled agencies
        m9_result = await db.execute(
            select(AgencyModule).where(
                AgencyModule.module_code == "M9",
                AgencyModule.is_active.is_(True),
            )
        )
        m9_modules = m9_result.scalars().all()

    if not m9_modules:
        logger.info("No agencies have M9 active — skipping ABM review")
        return

    for module in m9_modules:
        async with AsyncSessionLocal() as db:
            # Find accounts that are active and stale
            result = await db.execute(
                select(AbmAccount).where(
                    AbmAccount.agency_id == module.agency_id,
                    AbmAccount.stage.notin_(
                        ["closed_won", "closed_lost"]
                    ),
                )
            )
            accounts = result.scalars().all()

        stale_accounts = [
            a for a in accounts
            if not a.last_touch_at or a.last_touch_at < stale_threshold
        ]

        if not stale_accounts:
            logger.info(
                "Agency %s: no stale ABM accounts",
                module.agency_id,
            )
            continue

        logger.info(
            "Agency %s: running ABM orchestration for %d stale account(s)",
            module.agency_id,
            len(stale_accounts),
        )

        for account in stale_accounts:
            try:
                await run_abm_agent(
                    account_id=str(account.id),
                    agency_id=str(module.agency_id),
                )
            except Exception as e:
                logger.error(
                    "ABM agent failed for account %s: %s",
                    account.company_name,
                    e,
                )