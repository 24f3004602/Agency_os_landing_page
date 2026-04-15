import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_employee, require_owner
from app.core.gmail import send_email
from app.core.wati import send_whatsapp_message
from app.config import settings
from app.database import get_db
from app.modules.m1_workforce.models_communication import CommunicationLog
from app.modules.people_and_tenant.users.models import Client, Employee, User, UserRole
from app.modules.m1_workforce.schemas_communication import (
    CommunicationLogResponse,
    FlagReviewRequest,
    SendEmailRequest,
    SendWhatsAppRequest,
)

router = APIRouter(prefix="/communications", tags=["communications"])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_employee_for_user(user: User, db: AsyncSession) -> Employee:
    result = await db.execute(
        select(Employee).where(Employee.user_id == user.id)
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee profile not found")
    return emp


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


async def _build_log_response(
    log: CommunicationLog,
    db: AsyncSession,
) -> CommunicationLogResponse:
    employee_name = None
    if log.employee_id:
        emp_result = await db.execute(
            select(Employee).where(Employee.id == log.employee_id)
        )
        emp = emp_result.scalar_one_or_none()
        if emp:
            user_result = await db.execute(
                select(User).where(User.id == emp.user_id)
            )
            user = user_result.scalar_one_or_none()
            employee_name = user.full_name if user else None

    client_result = await db.execute(
        select(Client).where(Client.id == log.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"

    return CommunicationLogResponse(
        id=log.id,
        agency_id=log.agency_id,
        employee_id=log.employee_id,
        employee_name=employee_name,
        client_id=log.client_id,
        client_name=client_name,
        direction=log.direction,
        channel=log.channel,
        subject=log.subject,
        body=log.body,
        status=log.status,
        is_flagged=log.is_flagged,
        flag_reason=log.flag_reason,
        flag_reviewed=log.flag_reviewed,
        sent_at=log.sent_at,
        created_at=log.created_at,
    )


# ── Employee: Send Email ─────────────────────────────────────────────────────

@router.post("/send/email", response_model=CommunicationLogResponse)
async def send_client_email(
    body: SendEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
) -> CommunicationLogResponse:
    """
    Employee sends an email to a client.
    Logged to communication_logs automatically.
    Actual send requires Gmail OAuth token — stubbed if not configured.
    """
    employee = await _get_employee_for_user(current_user, db)
    client = await _get_client(body.client_id, employee.agency_id, db)

    now = datetime.now(timezone.utc)
    gmail_message_id = None
    send_status = "sent"

    # Attempt actual Gmail send
    if settings.gmail_client_id:
        try:
            # In production: fetch stored OAuth token from DB for this agency
            # For now: placeholder — real OAuth flow built in M2/Phase 6
            access_token = "PLACEHOLDER_OAUTH_TOKEN"
            result = await send_email(
                to_email=client.contact_email,
                subject=body.subject,
                body_html=body.body,
                access_token=access_token,
            )
            gmail_message_id = result.get("id")
        except Exception as e:
            send_status = "failed"
            import logging
            logging.getLogger(__name__).error("Gmail send failed: %s", e)
    else:
        import logging
        logging.getLogger(__name__).warning(
            "[GMAIL STUB] Email to %s: %s",
            client.contact_email,
            body.subject,
        )

    log = CommunicationLog(
        agency_id=employee.agency_id,
        employee_id=employee.id,
        client_id=client.id,
        direction="outbound",
        channel="email",
        subject=body.subject,
        body=body.body,
        status=send_status,
        gmail_message_id=gmail_message_id,
        sent_at=now,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    return await _build_log_response(log, db)


# ── Employee: Send WhatsApp ──────────────────────────────────────────────────

@router.post("/send/whatsapp", response_model=CommunicationLogResponse)
async def send_client_whatsapp(
    body: SendWhatsAppRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_employee)],
) -> CommunicationLogResponse:
    """
    Employee sends a WhatsApp message to a client via WATI.
    Logged automatically. Client phone from their profile.
    """
    employee = await _get_employee_for_user(current_user, db)
    client = await _get_client(body.client_id, employee.agency_id, db)

    if not client.contact_phone:
        raise HTTPException(
            400,
            "Client has no phone number on file. "
            "Update client profile with contact_phone first.",
        )

    now = datetime.now(timezone.utc)
    wati_message_id = None
    send_status = "sent"

    try:
        result = await send_whatsapp_message(
            phone_number=client.contact_phone,
            message=body.message,
        )
        wati_message_id = result.get("id")
    except Exception as e:
        send_status = "failed"
        import logging
        logging.getLogger(__name__).error("WATI send failed: %s", e)

    log = CommunicationLog(
        agency_id=employee.agency_id,
        employee_id=employee.id,
        client_id=client.id,
        direction="outbound",
        channel="whatsapp",
        body=body.message,
        status=send_status,
        wati_message_id=wati_message_id,
        sent_at=now,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    return await _build_log_response(log, db)


# ── Owner + Employee: Thread view ────────────────────────────────────────────

@router.get("/thread/{client_id}", response_model=list[CommunicationLogResponse])
async def get_thread(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    channel: str | None = None,  # filter by email | whatsapp
) -> list[CommunicationLogResponse]:
    """
    Returns full message thread with a client — both directions.
    Owner sees all threads. Employee sees only threads they're part of.
    """
    query = select(CommunicationLog).where(
        CommunicationLog.client_id == client_id,
        CommunicationLog.agency_id == current_user.agency_id,
    )

    if current_user.role == UserRole.EMPLOYEE:
        employee = await _get_employee_for_user(current_user, db)
        query = query.where(
            CommunicationLog.employee_id == employee.id
        )

    if channel:
        query = query.where(CommunicationLog.channel == channel)

    query = query.order_by(CommunicationLog.created_at.asc())
    result = await db.execute(query)
    logs = result.scalars().all()

    return [await _build_log_response(log, db) for log in logs]


# ── Owner: Flagged messages ──────────────────────────────────────────────────

@router.get("/flags", response_model=list[CommunicationLogResponse])
async def get_flagged_messages(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
    reviewed: bool | None = None,
) -> list[CommunicationLogResponse]:
    """
    Returns all messages flagged by the nightly audit agent.
    Filter by reviewed=false to see only unreviewed flags.
    """
    query = select(CommunicationLog).where(
        CommunicationLog.agency_id == current_user.agency_id,
        CommunicationLog.is_flagged.is_(True),
    )
    if reviewed is not None:
        query = query.where(
            CommunicationLog.flag_reviewed.is_(reviewed)
        )

    query = query.order_by(CommunicationLog.created_at.desc())
    result = await db.execute(query)
    logs = result.scalars().all()

    return [await _build_log_response(log, db) for log in logs]


# ── Owner: Mark flag as reviewed ─────────────────────────────────────────────

@router.patch("/flags/{log_id}/review", response_model=CommunicationLogResponse)
async def review_flag(
    log_id: uuid.UUID,
    body: FlagReviewRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_owner)],
) -> CommunicationLogResponse:
    result = await db.execute(
        select(CommunicationLog).where(
            CommunicationLog.id == log_id,
            CommunicationLog.agency_id == current_user.agency_id,
            CommunicationLog.is_flagged.is_(True),
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(404, "Flagged message not found")

    log.flag_reviewed = True
    log.flag_reviewed_at = datetime.now(timezone.utc)
    log.flag_reviewed_by = current_user.id

    await db.commit()
    await db.refresh(log)
    return await _build_log_response(log, db)


# ── Webhook: WATI inbound WhatsApp ───────────────────────────────────────────

@router.post("/webhooks/wati", status_code=200)
async def wati_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    WATI calls this endpoint when a client sends a WhatsApp message.
    Payload structure varies by WATI plan — we handle the common format.
    Configure this URL in your WATI dashboard as the webhook endpoint.
    n8n is NOT used here — WATI calls FastAPI directly.
    """
    payload = await request.json()

    # WATI webhook payload shape
    wati_message_id = payload.get("id") or payload.get("messageId")
    phone = payload.get("waId") or payload.get("from", "")
    message_text = payload.get("text", {}).get("body", "") or payload.get("body", "")
    event_type = payload.get("eventType", "")

    # Only process incoming messages
    if event_type not in ("", "message", "RECEIVED"):
        return {"status": "ignored", "reason": "not a message event"}

    if not message_text or not phone:
        return {"status": "ignored", "reason": "empty message or phone"}

    # Deduplicate — don't log the same WATI message twice
    if wati_message_id:
        existing = await db.execute(
            select(CommunicationLog).where(
                CommunicationLog.wati_message_id == wati_message_id
            )
        )
        if existing.scalar_one_or_none():
            return {"status": "duplicate", "message_id": wati_message_id}

    # Match phone to client
    # Normalize phone — strip spaces and ensure + prefix
    clean_phone = phone.strip().replace(" ", "")
    if not clean_phone.startswith("+"):
        clean_phone = f"+{clean_phone}"

    client_result = await db.execute(
        select(Client).where(Client.contact_phone == clean_phone)
    )
    client = client_result.scalar_one_or_none()

    if not client:
        # Unknown sender — log but mark as unmatched
        import logging
        logging.getLogger(__name__).warning(
            "WATI inbound from unknown phone %s — not matched to any client",
            clean_phone,
        )
        return {"status": "unmatched", "phone": clean_phone}

    log = CommunicationLog(
        agency_id=client.agency_id,
        employee_id=None,      # inbound — no employee sent this
        client_id=client.id,
        direction="inbound",
        channel="whatsapp",
        body=message_text,
        status="received",
        wati_message_id=wati_message_id,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.commit()

    return {"status": "logged", "client_id": str(client.id)}


# ── Webhook: Gmail inbound (called by n8n polling job) ───────────────────────

@router.post("/webhooks/gmail", status_code=200)
async def gmail_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    n8n calls this endpoint after polling Gmail and finding new replies.
    n8n extracts the message fields and sends them here.
    Expects payload: { gmail_message_id, from_email, subject, body, received_at }
    """
    payload = await request.json()

    gmail_message_id = payload.get("gmail_message_id")
    from_email = payload.get("from_email", "").lower().strip()
    subject = payload.get("subject", "")
    body = payload.get("body", "")

    if not gmail_message_id or not from_email or not body:
        return {"status": "ignored", "reason": "missing required fields"}

    # Deduplicate
    existing = await db.execute(
        select(CommunicationLog).where(
            CommunicationLog.gmail_message_id == gmail_message_id
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "gmail_message_id": gmail_message_id}

    # Match email to client
    client_result = await db.execute(
        select(Client).where(Client.contact_email == from_email)
    )
    client = client_result.scalar_one_or_none()

    if not client:
        return {"status": "unmatched", "from_email": from_email}

    log = CommunicationLog(
        agency_id=client.agency_id,
        employee_id=None,
        client_id=client.id,
        direction="inbound",
        channel="email",
        subject=subject,
        body=body,
        status="received",
        gmail_message_id=gmail_message_id,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.commit()

    return {"status": "logged", "client_id": str(client.id)}