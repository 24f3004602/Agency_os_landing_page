import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from celery_worker import celery_app
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.modules.m3_reporting.models import Report

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.m3_tasks.run_scheduled_reports", bind=True)
def run_scheduled_reports(self) -> dict:
    """Placeholder scheduler task for M3 until cron-driven report generation is finalized."""
    logger.info("[M3] Scheduled report scan triggered")
    return {"status": "ok", "message": "scheduled report scan executed"}


@celery_app.task(name="app.tasks.m3_tasks.schedule_report_followup", bind=True)
def schedule_report_followup(self, report_id: str) -> dict:
    """Marks follow-up sent if report has no client reply after the waiting window."""

    async def _run() -> dict:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Report).where(Report.id == uuid.UUID(report_id))
            )
            report = result.scalar_one_or_none()
            if not report:
                return {"status": "not_found", "report_id": report_id}

            if report.client_replied:
                return {"status": "skipped", "reason": "client_replied", "report_id": report_id}

            # Guard against accidental early execution.
            if report.delivered_at and report.delivered_at > datetime.now(timezone.utc) - timedelta(hours=48):
                return {"status": "skipped", "reason": "within_grace_period", "report_id": report_id}

            report.follow_up_sent = True
            await db.commit()
            return {"status": "ok", "report_id": report_id}

    return asyncio.run(_run())
