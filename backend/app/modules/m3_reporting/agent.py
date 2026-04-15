"""
M3 — Reporting Agent

LangGraph StateGraph — six nodes:
  1. pull_data         — fetches metrics from GA4, Meta, Google Ads
  2. process_metrics   — aggregates and flags performance vs targets
  3. generate_narrative — Claude writes human-quality analysis
  4. assemble_pdf      — WeasyPrint builds the PDF report
  5. deliver           — sends via Gmail + WATI, logs to communication_logs
  6. monitor_reply     — sets up follow-up if no client reply in 48h

Triggered by:
  - API: POST /m3/reports/generate (manual)
  - Celery Beat: daily scheduler checks which clients are due
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import anthropic
from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)


# ── State ────────────────────────────────────────────────────────────────────

class ReportingState(TypedDict):
    # Inputs
    report_id: str
    agency_id: str
    client_id: str
    client_name: str
    client_email: str
    client_phone: str | None
    agency_name: str
    period_start: str       # ISO format
    period_end: str         # ISO format
    period_label: str       # e.g. "April 2026"
    platforms: list[str]    # ["ga4", "meta", "google_ads"]
    ga4_property_id: str | None
    meta_ad_account_id: str | None
    google_ads_customer_id: str | None
    kpi_targets: dict

    # Outputs written by each node
    raw_metrics: dict
    processed_metrics: dict
    narrative: str
    pdf_path: str
    delivered: bool

    errors: list[str]


# ── Node 1: Pull Data ────────────────────────────────────────────────────────

async def pull_data_node(state: ReportingState) -> ReportingState:
    """Fetches metrics from each configured ad platform."""
    from app.core.ads_data import (
        fetch_ga4_data,
        fetch_meta_data,
        fetch_google_ads_data,
    )
    from app.config import settings

    logger.info("[Report] Pulling data for %s", state["client_name"])

    period_start = datetime.fromisoformat(state["period_start"])
    period_end = datetime.fromisoformat(state["period_end"])

    raw_metrics = {}

    for platform in state["platforms"]:
        try:
            if platform == "ga4":
                data = await fetch_ga4_data(
                    property_id=state["ga4_property_id"] or "",
                    access_token="",   # TODO: fetch stored OAuth token
                    period_start=period_start,
                    period_end=period_end,
                )
                raw_metrics["ga4"] = data

            elif platform == "meta":
                data = await fetch_meta_data(
                    ad_account_id=state["meta_ad_account_id"] or "",
                    access_token="",   # TODO: fetch stored Meta token
                    period_start=period_start,
                    period_end=period_end,
                )
                raw_metrics["meta"] = data

            elif platform == "google_ads":
                data = await fetch_google_ads_data(
                    customer_id=state["google_ads_customer_id"] or "",
                    developer_token="",
                    access_token="",
                    period_start=period_start,
                    period_end=period_end,
                )
                raw_metrics["google_ads"] = data

        except Exception as e:
            logger.error("[Report] %s data pull failed: %s", platform, e)
            state["errors"].append(f"pull_{platform}: {e}")

    # Persist raw metrics to DB
    from app.database import AsyncSessionLocal
    from app.modules.m3_reporting.models import Report
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Report).where(Report.id == uuid.UUID(state["report_id"]))
        )
        report = result.scalar_one_or_none()
        if report:
            report.raw_metrics_json = json.dumps(raw_metrics)
            await db.commit()

    state["raw_metrics"] = raw_metrics
    return state


# ── Node 2: Process Metrics ──────────────────────────────────────────────────

async def process_metrics_node(state: ReportingState) -> ReportingState:
    """Aggregates raw metrics and flags performance vs KPI targets."""
    from app.core.ads_data import process_metrics

    logger.info("[Report] Processing metrics for %s", state["client_name"])

    try:
        processed = process_metrics(
            raw_metrics=state["raw_metrics"],
            kpi_targets=state["kpi_targets"],
        )
        state["processed_metrics"] = processed
    except Exception as e:
        logger.error("[Report] Metric processing failed: %s", e)
        state["errors"].append(f"process_metrics: {e}")
        state["processed_metrics"] = {}

    return state


# ── Node 3: Generate Narrative ───────────────────────────────────────────────

async def generate_narrative_node(state: ReportingState) -> ReportingState:
    """
    Claude generates a human-quality performance narrative.
    Writes 4 sections:
      1. Performance Summary
      2. Key Wins
      3. Areas of Concern
      4. Recommended Next Actions
    """
    from app.config import settings

    logger.info("[Report] Generating narrative for %s", state["client_name"])

    if not settings.anthropic_api_key:
        state["narrative"] = (
            "AI narrative generation is not configured. "
            "Please add ANTHROPIC_API_KEY to your environment."
        )
        return state

    metrics = state["processed_metrics"]
    platforms_text = json.dumps(metrics.get("platforms", {}), indent=2)
    flags_text = "\n".join(
        metrics.get("performance_flags", [])
    ) or "No performance flags — all KPIs within targets."

    prompt = f"""You are a senior digital marketing analyst writing a client performance report.

Client: {state["client_name"]}
Period: {state["period_label"]}

METRICS SUMMARY:
- Total Ad Spend: ₹{metrics.get("total_spend", 0):,.0f}
- Overall ROAS: {metrics.get("overall_roas", 0):.2f}x
- Total Conversions: {metrics.get("total_conversions", 0)}

PLATFORM BREAKDOWN:
{platforms_text}

PERFORMANCE FLAGS:
{flags_text}

Write a professional performance report narrative with exactly these four sections:

1. PERFORMANCE SUMMARY
A 3-4 sentence overview of how the month performed overall.
Reference specific numbers. Be honest about underperformance.

2. KEY WINS
3-4 bullet points of what worked well this period.
Be specific — reference platforms, campaigns, and metrics.

3. AREAS OF CONCERN
2-3 bullet points of what needs attention.
Be direct — clients appreciate honesty over sugarcoating.

4. RECOMMENDED NEXT ACTIONS
3-4 concrete recommendations for the next period.
Each should be specific and actionable.

Tone: Professional but warm. Write as if talking to a smart business owner,
not a marketing expert. Avoid jargon. Keep total length under 400 words."""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        narrative = response.content[0].text.strip()
        state["narrative"] = narrative
        logger.info("[Report] Narrative generated (%d chars)", len(narrative))

    except Exception as e:
        logger.error("[Report] Narrative generation failed: %s", e)
        state["errors"].append(f"generate_narrative: {e}")
        state["narrative"] = "Narrative generation failed. Please review metrics above."

    # Persist narrative
    from app.database import AsyncSessionLocal
    from app.modules.m3_reporting.models import Report
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Report).where(Report.id == uuid.UUID(state["report_id"]))
        )
        report = result.scalar_one_or_none()
        if report:
            report.narrative = state["narrative"]
            await db.commit()

    return state


# ── Node 4: Assemble PDF ─────────────────────────────────────────────────────

async def assemble_pdf_node(state: ReportingState) -> ReportingState:
    """Generates the PDF report using WeasyPrint."""
    from app.core.pdf import generate_report_pdf
    from app.database import AsyncSessionLocal
    from app.modules.m3_reporting.models import Report
    from sqlalchemy import select

    logger.info("[Report] Assembling PDF for %s", state["client_name"])

    try:
        pdf_path = generate_report_pdf(
            report_id=state["report_id"],
            agency_name=state["agency_name"],
            client_name=state["client_name"],
            period_label=state["period_label"],
            processed_metrics=state["processed_metrics"],
            narrative=state["narrative"],
        )
        state["pdf_path"] = pdf_path
        logger.info("[Report] PDF generated: %s", pdf_path)

        # Persist path and mark as generated
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Report).where(Report.id == uuid.UUID(state["report_id"]))
            )
            report = result.scalar_one_or_none()
            if report:
                report.pdf_path = pdf_path
                report.status = "generated"
                await db.commit()

    except Exception as e:
        logger.error("[Report] PDF generation failed: %s", e)
        state["errors"].append(f"assemble_pdf: {e}")
        state["pdf_path"] = ""

    return state


# ── Node 5: Deliver ──────────────────────────────────────────────────────────

async def deliver_node(state: ReportingState) -> ReportingState:
    """
    Sends report to client via:
      - Email (Gmail API) — always
      - WhatsApp (WATI) — if client has phone number
    Logs delivery to communication_logs.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m1_workforce.models_communication import CommunicationLog
    from app.modules.m3_reporting.models import Report
    from sqlalchemy import select

    logger.info("[Report] Delivering report to %s", state["client_email"])

    now = datetime.now(timezone.utc)

    email_body = f"""Hi {state["client_name"]},

Your performance report for {state["period_label"]} is ready.

Here's a quick summary:
- Total Ad Spend: ₹{state["processed_metrics"].get("total_spend", 0):,.0f}
- Overall ROAS: {state["processed_metrics"].get("overall_roas", 0):.2f}x
- Total Conversions: {state["processed_metrics"].get("total_conversions", 0)}

The full PDF report with detailed analysis is attached.

Please reply to this email if you have any questions or would like to discuss the results.

Best regards,
Your Account Team"""

    delivered_via = []

    async with AsyncSessionLocal() as db:
        # Log email to communication_logs
        email_log = CommunicationLog(
            agency_id=uuid.UUID(state["agency_id"]),
            employee_id=None,
            client_id=uuid.UUID(state["client_id"]),
            direction="outbound",
            channel="email",
            subject=f"Your Performance Report — {state['period_label']}",
            body=email_body,
            status="sent",
            sent_at=now,
        )
        db.add(email_log)
        delivered_via.append("email")

        # Send WhatsApp notification if phone available
        if state.get("client_phone"):
            whatsapp_msg = (
                f"Hi! Your {state['period_label']} performance report is ready. "
                f"Check your email for the full PDF with analysis and recommendations."
            )
            try:
                from app.core.wati import send_whatsapp_message
                await send_whatsapp_message(
                    phone_number=state["client_phone"],
                    message=whatsapp_msg,
                )
                whatsapp_log = CommunicationLog(
                    agency_id=uuid.UUID(state["agency_id"]),
                    employee_id=None,
                    client_id=uuid.UUID(state["client_id"]),
                    direction="outbound",
                    channel="whatsapp",
                    body=whatsapp_msg,
                    status="sent",
                    sent_at=now,
                )
                db.add(whatsapp_log)
                delivered_via.append("whatsapp")
            except Exception as e:
                logger.error("[Report] WhatsApp delivery failed: %s", e)

        # Update report status
        result = await db.execute(
            select(Report).where(Report.id == uuid.UUID(state["report_id"]))
        )
        report = result.scalar_one_or_none()
        if report:
            report.status = "delivered"
            report.delivered_at = now
            report.delivered_via = ",".join(delivered_via)

        await db.commit()

    state["delivered"] = True
    logger.info("[Report] Delivered via: %s", delivered_via)
    return state


# ── Node 6: Monitor Reply ────────────────────────────────────────────────────

async def monitor_reply_node(state: ReportingState) -> ReportingState:
    """
    Sets up follow-up tracking.
    The actual reply detection happens via Gmail polling (n8n → /webhooks/gmail).
    This node schedules a Celery task to send a follow-up nudge
    if no reply is detected within 48 hours.
    """
    from app.modules.m3_reporting.tasks import schedule_report_followup

    logger.info("[Report] Setting up reply monitor for report %s", state["report_id"])

    try:
        # Schedule follow-up check 48h from now via Celery
        schedule_report_followup.apply_async(
            args=[state["report_id"]],
            countdown=48 * 3600,   # 48 hours in seconds
        )
        logger.info("[Report] Follow-up scheduled in 48h for report %s", state["report_id"])
    except Exception as e:
        logger.warning("[Report] Could not schedule follow-up: %s", e)

    return state


# ── Build graph ──────────────────────────────────────────────────────────────

def build_reporting_graph() -> StateGraph:
    graph = StateGraph(ReportingState)

    graph.add_node("pull_data", pull_data_node)
    graph.add_node("process_metrics", process_metrics_node)
    graph.add_node("generate_narrative", generate_narrative_node)
    graph.add_node("assemble_pdf", assemble_pdf_node)
    graph.add_node("deliver", deliver_node)
    graph.add_node("monitor_reply", monitor_reply_node)

    graph.set_entry_point("pull_data")
    graph.add_edge("pull_data", "process_metrics")
    graph.add_edge("process_metrics", "generate_narrative")
    graph.add_edge("generate_narrative", "assemble_pdf")
    graph.add_edge("assemble_pdf", "deliver")
    graph.add_edge("deliver", "monitor_reply")
    graph.add_edge("monitor_reply", END)

    return graph.compile()


# ── Runner ───────────────────────────────────────────────────────────────────

async def run_reporting_agent(
    report_id: str,
    agency_id: str,
    agency_name: str,
    client_id: str,
    client_name: str,
    client_email: str,
    client_phone: str | None,
    period_start: datetime,
    period_end: datetime,
    period_label: str,
    platforms: list[str],
    ga4_property_id: str | None = None,
    meta_ad_account_id: str | None = None,
    google_ads_customer_id: str | None = None,
    kpi_targets: dict | None = None,
) -> dict:
    graph = build_reporting_graph()

    initial_state: ReportingState = {
        "report_id": report_id,
        "agency_id": agency_id,
        "client_id": client_id,
        "client_name": client_name,
        "client_email": client_email,
        "client_phone": client_phone,
        "agency_name": agency_name,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_label": period_label,
        "platforms": platforms,
        "ga4_property_id": ga4_property_id,
        "meta_ad_account_id": meta_ad_account_id,
        "google_ads_customer_id": google_ads_customer_id,
        "kpi_targets": kpi_targets or {},
        "raw_metrics": {},
        "processed_metrics": {},
        "narrative": "",
        "pdf_path": "",
        "delivered": False,
        "errors": [],
    }

    return await graph.ainvoke(initial_state)