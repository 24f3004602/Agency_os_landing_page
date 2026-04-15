"""
M11 Celery Tasks — Campaign Orchestration Platform

Tasks:
  - send_approval_reminders : every 6 hours
                              finds pending approvals > 48h old
                              sends follow-up nudge to client
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


@celery_app.task(name="app.tasks.m11_tasks.send_approval_reminders", bind=True)
def send_approval_reminders(self):
    """Every 6 hours — nudges clients who haven't responded to approval requests."""
    logger.info("Starting approval reminder check")
    run_async(_send_approval_reminders_async())
    logger.info("Approval reminder check complete")


async def _send_approval_reminders_async() -> None:
    from sqlalchemy import select
    from app.modules.m11_content.models import ClientApprovalRequest, ContentDraft, ContentBrief
    from app.modules.people_and_tenant.users.models import Client
    from app.core.wati import send_whatsapp_message

    now = datetime.now(timezone.utc)
    reminder_threshold = now - timedelta(hours=48)
    max_reminders = 2   # never send more than 2 reminders

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ClientApprovalRequest).where(
                ClientApprovalRequest.status == "pending",
                ClientApprovalRequest.created_at <= reminder_threshold,
                ClientApprovalRequest.reminder_count < max_reminders,
            )
        )
        pending = result.scalars().all()

    if not pending:
        logger.info("No overdue approvals found")
        return

    logger.info("Found %d overdue approval(s)", len(pending))

    for approval in pending:
        async with AsyncSessionLocal() as db:
            # Get client details
            client_result = await db.execute(
                select(Client).where(Client.id == approval.client_id)
            )
            client = client_result.scalar_one_or_none()

            # Get draft + brief details
            draft_result = await db.execute(
                select(ContentDraft).where(ContentDraft.id == approval.draft_id)
            )
            draft = draft_result.scalar_one_or_none()

            brief = None
            if draft:
                brief_result = await db.execute(
                    select(ContentBrief).where(ContentBrief.id == draft.brief_id)
                )
                brief = brief_result.scalar_one_or_none()

            if not client or not draft or not brief:
                continue

            # Send WhatsApp reminder
            if client.contact_phone and approval.sent_via in ("whatsapp", "both"):
                days_waiting = (now - approval.created_at).days
                reminder_msg = (
                    f"Hi {client.contact_name or client.company_name}! 👋\n\n"
                    f"Just a gentle reminder — we're waiting on your approval for:\n"
                    f"*{brief.title}*\n\n"
                    f"It's been {days_waiting} day(s). "
                    f"Reply *APPROVE* or *REJECT* with feedback.\n\n"
                    f"Or log into your portal to review the drafts."
                )
                try:
                    await send_whatsapp_message(
                        phone_number=client.contact_phone,
                        message=reminder_msg,
                    )
                    logger.info(
                        "Reminder sent to %s for brief %s",
                        client.company_name,
                        brief.title,
                    )
                except Exception as e:
                    logger.warning("Reminder WhatsApp failed: %s", e)

            # Update reminder tracking
            from sqlalchemy import select as sel
            approval_result = await db.execute(
                sel(ClientApprovalRequest).where(
                    ClientApprovalRequest.id == approval.id
                )
            )
            approval_obj = approval_result.scalar_one_or_none()
            if approval_obj:
                approval_obj.reminder_count += 1
                approval_obj.reminder_sent_at = now
            await db.commit()