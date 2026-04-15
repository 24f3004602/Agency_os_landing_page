import calendar
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_module, require_owner, get_current_user
from app.core.pdf import MEDIA_ROOT
from app.database import get_db
from app.modules.people_and_tenant.agencies.models import Agency
from app.modules.m3_reporting.models import ClientReportConfig, Report
from app.modules.people_and_tenant.users.models import Client, UserRole
from app.modules.people_and_tenant.users.models import User
from app.modules.m3_reporting.schemas import (
    GenerateReportRequest,
    ReportConfigCreate,
    ReportConfigResponse,
    ReportResponse,
    ReportSummary,
)

router = APIRouter(prefix="/m3", tags=["M3 - Reporting"])

M3 = Depends(require_module("M3"))


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


async def _build_report_response(report: Report, db: AsyncSession) -> ReportResponse:
    client_result = await db.execute(
        select(Client).where(Client.id == report.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"

    # Build period label
    month_name = calendar.month_name[report.period_start.month]
    period_label = f"{month_name} {report.period_start.year}"

    # Parse metrics
    processed_metrics = None
    if report.raw_metrics_json:
        try:
            from app.core.ads_data import process_metrics
            raw = json.loads(report.raw_metrics_json)
            processed_metrics = process_metrics(raw)
        except Exception:
            processed_metrics = None

    return ReportResponse(
        id=report.id,
        agency_id=report.agency_id,
        client_id=report.client_id,
        client_name=client_name,
        period_start=report.period_start,
        period_end=report.period_end,
        period_label=period_label,
        status=report.status,
        narrative=report.narrative,
        processed_metrics=processed_metrics,
        has_pdf=report.pdf_path is not None,
        delivered_at=report.delivered_at,
        delivered_via=report.delivered_via,
        client_replied=report.client_replied,
        follow_up_sent=report.follow_up_sent,
        error_message=report.error_message,
        created_at=report.created_at,
    )


# ── Report Config: Create / Update ──────────────────────────────────────────

@router.post("/config/{client_id}", response_model=ReportConfigResponse)
async def set_report_config(
    client_id: uuid.UUID,
    body: ReportConfigCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M3],
) -> ReportConfigResponse:
    """
    Creates or updates reporting configuration for a client.
    Upsert — if config exists, updates it.
    """
    client = await _get_client(client_id, current_user.agency_id, db)

    existing = await db.execute(
        select(ClientReportConfig).where(
            ClientReportConfig.client_id == client_id,
            ClientReportConfig.agency_id == current_user.agency_id,
        )
    )
    config = existing.scalar_one_or_none()

    platforms_str = ",".join(body.platforms)
    kpi_json = json.dumps(body.kpi_targets) if body.kpi_targets else None

    if config:
        config.schedule = body.schedule
        config.platforms = platforms_str
        config.ga4_property_id = body.ga4_property_id
        config.meta_ad_account_id = body.meta_ad_account_id
        config.google_ads_customer_id = body.google_ads_customer_id
        config.kpi_targets_json = kpi_json
    else:
        config = ClientReportConfig(
            agency_id=current_user.agency_id,
            client_id=client_id,
            schedule=body.schedule,
            platforms=platforms_str,
            ga4_property_id=body.ga4_property_id,
            meta_ad_account_id=body.meta_ad_account_id,
            google_ads_customer_id=body.google_ads_customer_id,
            kpi_targets_json=kpi_json,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    kpi_targets = None
    if config.kpi_targets_json:
        try:
            kpi_targets = json.loads(config.kpi_targets_json)
        except Exception:
            pass

    return ReportConfigResponse(
        id=config.id,
        client_id=config.client_id,
        client_name=client.company_name,
        schedule=config.schedule,
        platforms=config.platforms.split(","),
        ga4_property_id=config.ga4_property_id,
        meta_ad_account_id=config.meta_ad_account_id,
        google_ads_customer_id=config.google_ads_customer_id,
        kpi_targets=kpi_targets,
        last_report_sent_at=config.last_report_sent_at,
        is_active=config.is_active,
        created_at=config.created_at,
    )


# ── Report Config: Get ───────────────────────────────────────────────────────

@router.get("/config/{client_id}", response_model=ReportConfigResponse)
async def get_report_config(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M3],
) -> ReportConfigResponse:
    client = await _get_client(client_id, current_user.agency_id, db)

    result = await db.execute(
        select(ClientReportConfig).where(
            ClientReportConfig.client_id == client_id,
            ClientReportConfig.agency_id == current_user.agency_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            404,
            "No report config found for this client. "
            "Create one with POST /m3/config/{client_id}",
        )

    kpi_targets = None
    if config.kpi_targets_json:
        try:
            kpi_targets = json.loads(config.kpi_targets_json)
        except Exception:
            pass

    return ReportConfigResponse(
        id=config.id,
        client_id=config.client_id,
        client_name=client.company_name,
        schedule=config.schedule,
        platforms=config.platforms.split(","),
        ga4_property_id=config.ga4_property_id,
        meta_ad_account_id=config.meta_ad_account_id,
        google_ads_customer_id=config.google_ads_customer_id,
        kpi_targets=kpi_targets,
        last_report_sent_at=config.last_report_sent_at,
        is_active=config.is_active,
        created_at=config.created_at,
    )


# ── Generate Report: Manually trigger ───────────────────────────────────────

@router.post("/reports/generate", response_model=ReportResponse, status_code=201)
async def generate_report(
    body: GenerateReportRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M3],
) -> ReportResponse:
    """
    Owner manually triggers report generation for a client.
    Returns immediately with a generating status report.
    Poll GET /m3/reports/{id} to check progress.
    """
    client = await _get_client(body.client_id, current_user.agency_id, db)

    # Fetch config for this client (optional — use defaults if missing)
    config_result = await db.execute(
        select(ClientReportConfig).where(
            ClientReportConfig.client_id == client.id,
            ClientReportConfig.agency_id == current_user.agency_id,
        )
    )
    config = config_result.scalar_one_or_none()

    platforms = body.platforms or (
        config.platforms.split(",") if config else ["ga4", "meta", "google_ads"]
    )

    # Fetch agency name
    agency_result = await db.execute(
        select(Agency).where(Agency.id == current_user.agency_id)
    )
    agency = agency_result.scalar_one_or_none()
    agency_name = agency.name if agency else "Agency"

    # Build period label
    month_name = calendar.month_name[body.period_start.month]
    period_label = f"{month_name} {body.period_start.year}"

    # Create report record
    report = Report(
        agency_id=current_user.agency_id,
        client_id=client.id,
        period_start=body.period_start,
        period_end=body.period_end,
        status="generating",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    kpi_targets = {}
    if config and config.kpi_targets_json:
        try:
            kpi_targets = json.loads(config.kpi_targets_json)
        except Exception:
            pass

    report_id = str(report.id)

    async def _run():
        from app.modules.m3_reporting.agent import run_reporting_agent
        await run_reporting_agent(
            report_id=report_id,
            agency_id=str(current_user.agency_id),
            agency_name=agency_name,
            client_id=str(client.id),
            client_name=client.company_name,
            client_email=client.contact_email,
            client_phone=client.contact_phone,
            period_start=body.period_start,
            period_end=body.period_end,
            period_label=period_label,
            platforms=platforms,
            ga4_property_id=config.ga4_property_id if config else None,
            meta_ad_account_id=config.meta_ad_account_id if config else None,
            google_ads_customer_id=config.google_ads_customer_id if config else None,
            kpi_targets=kpi_targets,
        )

    background_tasks.add_task(_run)

    return await _build_report_response(report, db)


# ── List reports ─────────────────────────────────────────────────────────────

@router.get("/reports", response_model=list[ReportSummary])
async def list_reports(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M3],
    client_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[ReportSummary]:
    query = select(Report).where(Report.agency_id == current_user.agency_id)
    if client_id:
        query = query.where(Report.client_id == client_id)
    if status:
        query = query.where(Report.status == status)
    query = query.order_by(Report.created_at.desc())

    result = await db.execute(query)
    reports = result.scalars().all()

    summaries = []
    for r in reports:
        client_result = await db.execute(
            select(Client).where(Client.id == r.client_id)
        )
        client = client_result.scalar_one_or_none()
        summaries.append(ReportSummary(
            id=r.id,
            client_id=r.client_id,
            client_name=client.company_name if client else "Unknown",
            period_start=r.period_start,
            period_end=r.period_end,
            status=r.status,
            has_pdf=r.pdf_path is not None,
            delivered_at=r.delivered_at,
            created_at=r.created_at,
        ))

    return summaries


# ── Get single report ────────────────────────────────────────────────────────

@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M3],
) -> ReportResponse:
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.agency_id == current_user.agency_id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    return await _build_report_response(report, db)


# ── Download PDF ─────────────────────────────────────────────────────────────

@router.get("/reports/{report_id}/pdf")
async def download_report_pdf(
    report_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Owner downloads any report PDF.
    Client can download their own reports (client portal — Dashboard 3).
    """
    result = await db.execute(
        select(Report).where(Report.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    # Access control
    if current_user.role == UserRole.CLIENT:
        # Verify this report belongs to this client's agency
        if report.agency_id != current_user.agency_id:
            raise HTTPException(403, "Access denied")
    elif current_user.role in [UserRole.OWNER, UserRole.SUPERADMIN]:
        if (current_user.role == UserRole.OWNER
                and report.agency_id != current_user.agency_id):
            raise HTTPException(403, "Report does not belong to your agency")

    if not report.pdf_path:
        raise HTTPException(404, "PDF not yet generated")

    abs_path = MEDIA_ROOT / report.pdf_path
    if not abs_path.exists():
        raise HTTPException(404, "PDF file not found on server")

    client_result = await db.execute(
        select(Client).where(Client.id == report.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = (client.company_name or "client").replace(" ", "_") if client else "client"

    month_name = calendar.month_name[report.period_start.month]
    filename = f"report_{client_name}_{month_name}_{report.period_start.year}.pdf"

    return FileResponse(
        path=str(abs_path),
        media_type="application/pdf",
        filename=filename,
    )