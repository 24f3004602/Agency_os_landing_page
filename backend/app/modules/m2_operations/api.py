import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_module, require_owner
from app.core.pdf import MEDIA_ROOT, generate_invoice_pdf
from app.database import get_db
from app.modules.m2_operations.models import Invoice, OnboardingFlow, OnboardingStep
from app.modules.people_and_tenant.users.models import Client, Employee, User
from app.modules.m2_operations.schemas import (
    InvoiceCreate,
    InvoiceResponse,
    InvoiceStatusUpdate,
    OnboardingFlowResponse,
    OnboardingStepResponse,
    TriggerOnboardingRequest,
)

router = APIRouter(prefix="/m2", tags=["M2 - Operations"])

# ── All routes in this file require M2 to be active ─────────────────────────
M2 = Depends(require_module("M2"))


# ── Helpers ──────────────────────────────────────────────────────────────────

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


def _next_invoice_number(existing_count: int) -> str:
    """Generates INV-0001, INV-0002 etc."""
    return f"INV-{existing_count + 1:04d}"


async def _build_invoice_response(
    invoice: Invoice, db: AsyncSession
) -> InvoiceResponse:
    client_result = await db.execute(
        select(Client).where(Client.id == invoice.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"

    return InvoiceResponse(
        id=invoice.id,
        agency_id=invoice.agency_id,
        client_id=invoice.client_id,
        client_name=client_name,
        invoice_number=invoice.invoice_number,
        status=invoice.status,
        line_items=json.loads(invoice.line_items_json),
        subtotal=invoice.subtotal,
        tax_percent=invoice.tax_percent,
        tax_amount=invoice.tax_amount,
        total_amount=invoice.total_amount,
        due_date=invoice.due_date,
        paid_at=invoice.paid_at,
        notes=invoice.notes,
        has_pdf=invoice.pdf_path is not None,
        created_at=invoice.created_at,
    )


# ── Onboarding: Trigger ──────────────────────────────────────────────────────

@router.post("/onboarding/trigger", response_model=OnboardingFlowResponse)
async def trigger_onboarding(
    body: TriggerOnboardingRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M2],
) -> OnboardingFlowResponse:
    """
    Owner manually triggers onboarding for a client.
    Creates an OnboardingFlow record and runs the LangGraph
    agent in the background — returns immediately with flow id.
    """
    client = await _get_client(body.client_id, current_user.agency_id, db)

    # Prevent duplicate active onboardings
    existing = await db.execute(
        select(OnboardingFlow).where(
            OnboardingFlow.client_id == client.id,
            OnboardingFlow.status.in_(["pending", "in_progress"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            409,
            "An onboarding flow is already active for this client",
        )

    # Get account manager name
    am_name = "Your Account Manager"
    if client.account_manager_id:
        emp_result = await db.execute(
            select(Employee).where(Employee.id == client.account_manager_id)
        )
        emp = emp_result.scalar_one_or_none()
        if emp:
            user_result = await db.execute(
                select(User).where(User.id == emp.user_id)
            )
            u = user_result.scalar_one_or_none()
            am_name = u.full_name if u else am_name

    # Create flow record
    flow = OnboardingFlow(
        agency_id=current_user.agency_id,
        client_id=client.id,
        status="pending",
        hubspot_deal_id=client.hubspot_deal_id,
    )
    db.add(flow)
    await db.commit()
    await db.refresh(flow)

    # Run agent in background so API returns immediately
    async def _run():
        from app.modules.m2_operations.agent import run_onboarding_agent
        await run_onboarding_agent(
            flow_id=str(flow.id),
            agency_id=str(current_user.agency_id),
            client_id=str(client.id),
            client_name=client.company_name,
            client_email=client.contact_email,
            account_manager_name=am_name,
            deal_notes=body.deal_notes or "",
        )

    background_tasks.add_task(_run)

    return OnboardingFlowResponse(
        id=flow.id,
        client_id=flow.client_id,
        client_name=client.company_name,
        status=flow.status,
        client_brief=None,
        last_completed_node=None,
        error_message=None,
        steps=[],
        created_at=flow.created_at,
    )


# ── Onboarding: Status ───────────────────────────────────────────────────────

@router.get("/onboarding/{client_id}", response_model=OnboardingFlowResponse)
async def get_onboarding_status(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M2],
) -> OnboardingFlowResponse:
    """Poll this after triggering onboarding to check agent progress."""
    client = await _get_client(client_id, current_user.agency_id, db)

    result = await db.execute(
        select(OnboardingFlow)
        .where(OnboardingFlow.client_id == client.id)
        .order_by(OnboardingFlow.created_at.desc())
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(404, "No onboarding flow found for this client")

    await db.refresh(flow, ["steps"])

    return OnboardingFlowResponse(
        id=flow.id,
        client_id=flow.client_id,
        client_name=client.company_name,
        status=flow.status,
        client_brief=flow.client_brief,
        last_completed_node=flow.last_completed_node,
        error_message=flow.error_message,
        steps=[OnboardingStepResponse.model_validate(s) for s in flow.steps],
        created_at=flow.created_at,
    )


# ── HubSpot Webhook ──────────────────────────────────────────────────────────

@router.post("/webhooks/hubspot", status_code=200)
async def hubspot_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    n8n calls this when a HubSpot deal is marked Closed Won.
    n8n extracts the deal fields and sends them here.
    Expected payload:
    {
      "deal_id": "...",
      "company_name": "...",
      "contact_email": "...",
      "contact_name": "...",
      "deal_notes": "...",
      "agency_id": "..."   ← n8n adds this from webhook config
    }
    """
    payload = await request.json()

    agency_id_str = payload.get("agency_id")
    deal_id = payload.get("deal_id")
    company_name = payload.get("company_name", "Unknown")
    contact_email = payload.get("contact_email", "")
    contact_name = payload.get("contact_name", "")
    deal_notes = payload.get("deal_notes", "")

    if not agency_id_str or not contact_email:
        return {"status": "ignored", "reason": "missing agency_id or contact_email"}

    agency_id = uuid.UUID(agency_id_str)

    # Find or create client
    client_result = await db.execute(
        select(Client).where(
            Client.contact_email == contact_email.lower(),
            Client.agency_id == agency_id,
        )
    )
    client = client_result.scalar_one_or_none()

    if not client:
        client = Client(
            agency_id=agency_id,
            company_name=company_name,
            contact_name=contact_name,
            contact_email=contact_email.lower(),
            hubspot_deal_id=deal_id,
            status="active",
        )
        db.add(client)
        await db.commit()
        await db.refresh(client)

    # Create and trigger onboarding flow
    flow = OnboardingFlow(
        agency_id=agency_id,
        client_id=client.id,
        status="pending",
        hubspot_deal_id=deal_id,
    )
    db.add(flow)
    await db.commit()
    await db.refresh(flow)

    async def _run():
        from app.modules.m2_operations.agent import run_onboarding_agent
        await run_onboarding_agent(
            flow_id=str(flow.id),
            agency_id=str(agency_id),
            client_id=str(client.id),
            client_name=client.company_name,
            client_email=client.contact_email,
            account_manager_name="Account Manager",
            deal_notes=deal_notes,
        )

    background_tasks.add_task(_run)

    return {
        "status": "onboarding_triggered",
        "flow_id": str(flow.id),
        "client_id": str(client.id),
    }


# ── Invoices: Create ─────────────────────────────────────────────────────────

@router.post("/invoices", response_model=InvoiceResponse, status_code=201)
async def create_invoice(
    body: InvoiceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M2],
) -> InvoiceResponse:
    client = await _get_client(body.client_id, current_user.agency_id, db)

    # Calculate totals
    subtotal = sum(
        item.unit_price * item.quantity for item in body.line_items
    )
    tax_amount = (subtotal * body.tax_percent / 100).quantize(Decimal("0.01"))
    total_amount = subtotal + tax_amount

    # Generate invoice number
    count_result = await db.execute(
        select(Invoice).where(Invoice.agency_id == current_user.agency_id)
    )
    existing_count = len(count_result.scalars().all())
    invoice_number = _next_invoice_number(existing_count)

    # Serialise line items
    line_items_data = [item.model_dump() for item in body.line_items]
    for item in line_items_data:
        item["unit_price"] = float(item["unit_price"])

    invoice = Invoice(
        agency_id=current_user.agency_id,
        client_id=client.id,
        invoice_number=invoice_number,
        status="sent" if body.send_immediately else "draft",
        line_items_json=json.dumps(line_items_data),
        subtotal=subtotal.quantize(Decimal("0.01")),
        tax_percent=body.tax_percent,
        tax_amount=tax_amount,
        total_amount=total_amount.quantize(Decimal("0.01")),
        due_date=body.due_date,
        notes=body.notes,
    )
    db.add(invoice)
    await db.flush()

    # Get agency name for PDF
    from app.modules.people_and_tenant.agencies.models import Agency
    agency_result = await db.execute(
        select(Agency).where(Agency.id == current_user.agency_id)
    )
    agency = agency_result.scalar_one_or_none()
    agency_name = agency.name if agency else "Agency"

    # Generate PDF
    due_date_str = body.due_date.strftime("%d %b %Y") if body.due_date else None
    pdf_path = generate_invoice_pdf(
        invoice_id=str(invoice.id),
        invoice_number=invoice_number,
        agency_name=agency_name,
        client_company=client.company_name,
        client_contact=client.contact_name,
        client_email=client.contact_email,
        status=invoice.status,
        line_items=line_items_data,
        subtotal=invoice.subtotal,
        tax_percent=invoice.tax_percent,
        tax_amount=invoice.tax_amount,
        total_amount=invoice.total_amount,
        due_date=due_date_str,
        notes=body.notes,
    )
    invoice.pdf_path = pdf_path

    await db.commit()
    await db.refresh(invoice)
    return await _build_invoice_response(invoice, db)


# ── Invoices: List ───────────────────────────────────────────────────────────

@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M2],
    status: str | None = None,
    client_id: uuid.UUID | None = None,
) -> list[InvoiceResponse]:
    query = select(Invoice).where(Invoice.agency_id == current_user.agency_id)
    if status:
        query = query.where(Invoice.status == status)
    if client_id:
        query = query.where(Invoice.client_id == client_id)
    query = query.order_by(Invoice.created_at.desc())

    result = await db.execute(query)
    invoices = result.scalars().all()
    return [await _build_invoice_response(inv, db) for inv in invoices]


# ── Invoices: Get one ────────────────────────────────────────────────────────

@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M2],
) -> InvoiceResponse:
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.agency_id == current_user.agency_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    return await _build_invoice_response(invoice, db)


# ── Invoices: Update status ──────────────────────────────────────────────────

@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceResponse)
async def update_invoice_status(
    invoice_id: uuid.UUID,
    body: InvoiceStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M2],
) -> InvoiceResponse:
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.agency_id == current_user.agency_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    invoice.status = body.status
    if body.status == "paid":
        invoice.paid_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(invoice)
    return await _build_invoice_response(invoice, db)


# ── Invoices: Download PDF ───────────────────────────────────────────────────

@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M2],
):
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.agency_id == current_user.agency_id,
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(404, "Invoice not found")

    if not invoice.pdf_path:
        raise HTTPException(404, "PDF not yet generated")

    abs_path = MEDIA_ROOT / invoice.pdf_path
    if not abs_path.exists():
        raise HTTPException(404, "PDF file not found on server")

    return FileResponse(
        path=str(abs_path),
        media_type="application/pdf",
        filename=f"{invoice.invoice_number}.pdf",
    )