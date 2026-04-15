"""
M8 Celery Tasks — Personalisation & Outreach Agent

Tasks:
  - send_scheduled_steps : runs every hour
                           finds OutreachStep rows where:
                             status=pending AND
                             scheduled_send_at <= now AND
                             sequence.status=active
                           sends each step via appropriate channel
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


@celery_app.task(name="app.tasks.m8_tasks.send_scheduled_steps", bind=True)
def send_scheduled_steps(self):
    """
    Runs every hour.
    Finds outreach steps that are due to send and dispatches them.
    Skips steps in paused or completed sequences.
    Skips manual-mode steps not yet approved by AE.
    """
    logger.info("Starting outreach step scheduler")
    run_async(_send_scheduled_steps_async())
    logger.info("Outreach step scheduler complete")


async def _send_scheduled_steps_async() -> None:
    from sqlalchemy import select, and_
    from app.modules.m8_outreach.models import OutreachStep, OutreachSequence
    from app.modules.m7_leads.models import Lead
    from app.modules.m1_workforce.models_communication import CommunicationLog

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Find all pending steps that are due
        result = await db.execute(
            select(OutreachStep).where(
                OutreachStep.status == "pending",
                OutreachStep.scheduled_send_at <= now,
                OutreachStep.approved_by_ae.is_(True),
            )
        )
        due_steps = result.scalars().all()

    if not due_steps:
        logger.info("No outreach steps due for sending")
        return

    logger.info("Found %d step(s) due for sending", len(due_steps))

    for step in due_steps:
        async with AsyncSessionLocal() as db:
            # Verify sequence is still active
            seq_result = await db.execute(
                select(OutreachSequence).where(
                    OutreachSequence.id == step.sequence_id
                )
            )
            sequence = seq_result.scalar_one_or_none()

            if not sequence or sequence.status not in ("active",):
                logger.info(
                    "Skipping step %s — sequence status: %s",
                    step.id,
                    sequence.status if sequence else "not found",
                )
                continue

            # Get lead email for sending
            lead_result = await db.execute(
                select(Lead).where(Lead.id == sequence.lead_id)
            )
            lead = lead_result.scalar_one_or_none()
            if not lead:
                continue

            # Send based on channel
            if step.channel == "email":
                # Log to communication_logs
                log = CommunicationLog(
                    agency_id=step.agency_id,
                    employee_id=None,
                    client_id=sequence.lead_id,
                    direction="outbound",
                    channel="email",
                    subject=step.subject,
                    body=step.body,
                    status="sent",
                    sent_at=now,
                )
                db.add(log)

                # TODO: call Gmail API with stored OAuth token
                logger.warning(
                    "[GMAIL STUB] Outreach step %d to %s: %s",
                    step.step_number,
                    lead.email,
                    step.subject,
                )

            elif step.channel == "linkedin":
                logger.warning(
                    "[LINKEDIN STUB] Step %d LinkedIn message to %s ready",
                    step.step_number,
                    lead.full_name,
                )

            # Mark step as sent
            step_fetch = await db.execute(
                select(OutreachStep).where(OutreachStep.id == step.id)
            )
            step_obj = step_fetch.scalar_one_or_none()
            if step_obj:
                step_obj.status = "sent"
                step_obj.sent_at = now

            # Advance sequence to next step
            next_step_number = step.step_number + 1
            if next_step_number > sequence.total_steps:
                sequence.status = "completed"
                logger.info(
                    "Sequence %s completed for lead %s",
                    sequence.id,
                    sequence.lead_id,
                )
            else:
                sequence.current_step = next_step_number

            await db.commit()