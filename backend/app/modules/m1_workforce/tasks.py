"""
M1 Celery Tasks — Workforce Intelligence

Tasks registered here:
  - flag_incomplete_sessions   : runs nightly at 23:00 IST
                                  finds open sessions from today, marks them
                                  incomplete, notifies owner via Slack
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import select, func

from celery_worker import celery_app
from app.database import AsyncSessionLocal
from app.modules.m1_workforce.models_attendance import AttendanceSession
from app.modules.people_and_tenant.users.models import Employee, User
from app.modules.people_and_tenant.agencies.models import Agency
from sqlalchemy import select, func
from app.config import settings

logger = logging.getLogger(__name__)


# ─── Helper: run async code inside a Celery task ──────────────────────────────

def run_async(coro):
    """Celery workers are sync. This bridges async DB calls."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Slack notifier (stub — full Slack SDK integration in M1 Phase 4) ─────────

async def _notify_owner_incomplete_sessions(
    agency_name: str,
    owner_email: str,
    flagged: list[dict],
) -> None:
    """
    Sends a Slack message to the owner listing employees with incomplete sessions.
    Stub for now — Slack SDK wired in Phase 4 when we set up the notification bus.
    """
    # TODO Phase 4: replace with real Slack SDK call
    summary = "\n".join(
        [f"  • {item['employee_name']} — clocked in at {item['clock_in_time']}" for item in flagged]
    )
    logger.warning(
        "[SLACK STUB] %s — Incomplete attendance sessions:\n%s",
        agency_name,
        summary,
    )


# ─── Task: Flag Incomplete Sessions ───────────────────────────────────────────

@celery_app.task(name="app.tasks.m1_tasks.flag_incomplete_sessions", bind=True)
def flag_incomplete_sessions(self):
    """
    Nightly job — 23:00 IST.

    Finds all AttendanceSession rows where:
      - status = 'open'
      - clock_in_time is today (UTC date, accounting for IST offset)

    For each found:
      1. Marks status = 'incomplete'
      2. Leaves hours_worked as NULL (owner can manually correct)
      3. Collects employee info and sends owner alert

    Runs per agency — every agency's incomplete sessions are flagged independently.
    """
    logger.info("Starting flag_incomplete_sessions task")
    run_async(_flag_incomplete_sessions_async())
    logger.info("Completed flag_incomplete_sessions task")


async def _flag_incomplete_sessions_async() -> None:
    async with AsyncSessionLocal() as db:
        # IST is UTC+5:30 — 23:00 IST = 17:30 UTC
        # We look for sessions clocked in today in UTC terms
        now_utc = datetime.now(timezone.utc)
        today_utc = now_utc.date()

        # Find all open sessions from today
        result = await db.execute(
            select(AttendanceSession).where(
                AttendanceSession.status == "open",
                func.date(AttendanceSession.clock_in_time) == today_utc,
            )
        )
        open_sessions = result.scalars().all()

        if not open_sessions:
            logger.info("No incomplete sessions found for today (%s)", today_utc)
            return

        logger.info("Found %d incomplete session(s) — flagging now", len(open_sessions))

        # Group by agency for notification batching
        agency_sessions: dict[str, list] = {}
        for session in open_sessions:
            agency_key = str(session.agency_id)
            if agency_key not in agency_sessions:
                agency_sessions[agency_key] = []
            agency_sessions[agency_key].append(session)

        # Process each agency
        for agency_id_str, sessions in agency_sessions.items():
            flagged_details = []

            for session in sessions:
                # Mark incomplete
                session.status = "incomplete"
                session.notes = (
                    session.notes or ""
                ) + f"\n[AUTO] Flagged incomplete by nightly job at {now_utc.isoformat()}"

                # Fetch employee name for notification
                emp_result = await db.execute(
                    select(Employee).where(Employee.id == session.employee_id)
                )
                employee = emp_result.scalar_one_or_none()

                employee_name = "Unknown"
                if employee:
                    user_result = await db.execute(
                        select(User).where(User.id == employee.user_id)
                    )
                    user = user_result.scalar_one_or_none()
                    employee_name = user.full_name if user else "Unknown"

                flagged_details.append({
                    "employee_name": employee_name,
                    "clock_in_time": session.clock_in_time.strftime("%H:%M UTC"),
                    "session_id": str(session.id),
                })

            await db.commit()

            # Fetch agency info for the notification
            agency_result = await db.execute(
                select(Agency).where(Agency.id == session.agency_id)
            )
            agency = agency_result.scalar_one_or_none()
            agency_name = agency.name if agency else agency_id_str
            owner_email = agency.owner_email if agency else "unknown"

            # Send owner notification
            await _notify_owner_incomplete_sessions(
                agency_name=agency_name,
                owner_email=owner_email,
                flagged=flagged_details,
            )

            logger.info(
                "Agency '%s': flagged %d incomplete session(s)",
                agency_name,
                len(sessions),
            )


# ─── Task: Deadline Reminders ─────────────────────────────────────────────────

@celery_app.task(name="app.tasks.m1_tasks.send_deadline_reminders", bind=True)
def send_deadline_reminders(self):
    """
    Runs every morning at 09:00 IST.
    Finds tasks due within the next 24 hours that are not yet submitted.
    Sends a reminder notification to the assigned employee.
    """
    logger.info("Starting send_deadline_reminders task")
    run_async(_send_deadline_reminders_async())
    logger.info("Completed send_deadline_reminders task")


async def _send_deadline_reminders_async() -> None:
    from app.modules.m1_workforce.models_task import Task
    from datetime import timedelta

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(hours=24)

        result = await db.execute(
            select(Task).where(
                Task.deadline >= now,
                Task.deadline <= window_end,
                Task.status.in_(["created", "in_progress"]),
            )
        )
        tasks = result.scalars().all()

        if not tasks:
            logger.info("No upcoming deadlines in next 24h")
            return

        for task in tasks:
            # Get employee details for notification
            emp_result = await db.execute(
                select(Employee).where(Employee.id == task.assigned_to)
            )
            employee = emp_result.scalar_one_or_none()
            if not employee:
                continue

            user_result = await db.execute(
                select(User).where(User.id == employee.user_id)
            )
            user = user_result.scalar_one_or_none()
            employee_name = user.full_name if user else "Unknown"

            hours_left = (task.deadline - now).total_seconds() / 3600

            # TODO Phase 4: replace with Slack SDK call
            logger.warning(
                "[SLACK STUB] Deadline reminder → %s: Task '%s' due in %.1fh",
                employee_name,
                task.title,
                hours_left,
            )


# ─── Task: Overdue Escalation ─────────────────────────────────────────────────

@celery_app.task(name="app.tasks.m1_tasks.escalate_overdue_tasks", bind=True)
def escalate_overdue_tasks(self):
    """
    Runs every hour.
    Finds tasks past their deadline still in created/in_progress.
    Marks them overdue and alerts the owner.
    """
    logger.info("Starting escalate_overdue_tasks")
    run_async(_escalate_overdue_tasks_async())
    logger.info("Completed escalate_overdue_tasks")


async def _escalate_overdue_tasks_async() -> None:
    from app.modules.m1_workforce.models_task import Task
    from app.modules.people_and_tenant.agencies.models import Agency

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(Task).where(
                Task.deadline < now,
                Task.status.in_(["created", "in_progress"]),
            )
        )
        overdue_tasks = result.scalars().all()

        if not overdue_tasks:
            return

        logger.info("Found %d overdue task(s) — escalating", len(overdue_tasks))

        # Group by agency for batched owner alerts
        agency_groups: dict[str, list[Task]] = {}
        for task in overdue_tasks:
            key = str(task.agency_id)
            agency_groups.setdefault(key, []).append(task)
            task.status = "overdue"

        await db.commit()

        for agency_id_str, tasks in agency_groups.items():
            agency_result = await db.execute(
                select(Agency).where(Agency.id == tasks[0].agency_id)
            )
            agency = agency_result.scalar_one_or_none()
            agency_name = agency.name if agency else agency_id_str

            task_titles = [f"  • {t.title}" for t in tasks]
            # TODO Phase 4: replace with Slack SDK call to owner
            logger.warning(
                "[SLACK STUB] Overdue alert → owner of '%s': %d task(s) overdue:\n%s",
                agency_name,
                len(tasks),
                "\n".join(task_titles),
            )
            
# ─── Communication Audit Agent ────────────────────────────────────────────────

@celery_app.task(name="app.tasks.m1_tasks.audit_communications", bind=True)
def audit_communications(self):
    """
    Runs nightly at 02:00 IST.
    Scans all outbound messages sent today across all agencies.
    Uses Claude to flag messages that contain:
      - Personal contact sharing (personal phone/email)
      - Off-platform redirect attempts
      - Unauthorised pricing discussions
    Flags are written back to communication_logs.
    Owner sees them in GET /communications/flags.
    """
    logger.info("Starting communication audit agent")
    run_async(_audit_communications_async())
    logger.info("Completed communication audit agent")


async def _audit_communications_async() -> None:
    from datetime import date, timedelta
    from app.modules.m1_workforce.models_communication import CommunicationLog
    import anthropic

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping audit")
        return

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async with AsyncSessionLocal() as db:
        today = datetime.now(timezone.utc).date()

        # Fetch all outbound messages from today not yet audited
        result = await db.execute(
            select(CommunicationLog).where(
                CommunicationLog.direction == "outbound",
                CommunicationLog.is_flagged.is_(False),
                func.date(CommunicationLog.created_at) == today,
            )
        )
        messages = result.scalars().all()

        if not messages:
            logger.info("No outbound messages to audit today")
            return

        logger.info("Auditing %d outbound messages", len(messages))

        for msg in messages:
            # Build prompt for Claude
            prompt = f"""You are a compliance auditor for a digital marketing agency.
Review the following message sent by an agency employee to a client.

Flag it ONLY if it clearly contains one or more of these violations:
1. PERSONAL_CONTACT: Sharing personal phone number or personal email
2. OFF_PLATFORM: Asking client to move to WhatsApp, Telegram, or other personal channels outside the platform
3. PRICING: Discussing unauthorised pricing, discounts, or payment outside official invoices

Message:
---
Subject: {msg.subject or '(no subject)'}
Body: {msg.body}
---

Respond ONLY in this exact JSON format with no other text:
{{
  "flagged": true or false,
  "reason": "brief explanation if flagged, empty string if not",
  "violation_type": "PERSONAL_CONTACT | OFF_PLATFORM | PRICING | null"
}}"""

            try:
                response = client.messages.create(
                    model="claude-haiku-4-5",
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )

                import json
                result_text = response.content[0].text.strip()
                audit_result = json.loads(result_text)

                if audit_result.get("flagged"):
                    msg.is_flagged = True
                    msg.flag_reason = (
                        f"[{audit_result.get('violation_type', 'UNKNOWN')}] "
                        f"{audit_result.get('reason', '')}"
                    )
                    logger.warning(
                        "Flagged message %s: %s",
                        msg.id,
                        msg.flag_reason,
                    )

            except Exception as e:
                logger.error("Audit failed for message %s: %s", msg.id, e)
                continue

        await db.commit()
        logger.info("Audit complete")