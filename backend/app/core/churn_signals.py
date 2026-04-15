"""
Signal collectors for the Churn Prevention Agent.

Each function fetches a specific category of signals for a client
and returns a list of plain-English signal descriptions + a raw
weight score (0-100) for that category.

The agent combines all signals and passes them to Claude for
final risk scoring and retention action generation.
"""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Performance signals (from M3 reports) ───────────────────────────────────

async def get_performance_signals(
    client_id,
    db: AsyncSession,
) -> tuple[list[str], float]:
    """
    Checks last 2 report periods for declining performance.
    Returns (signal_descriptions, weight_score 0-40)
    """
    from app.modules.m3_reporting.models import Report
    import json

    signals = []
    weight = 0.0

    result = await db.execute(
        select(Report).where(
            Report.client_id == client_id,
            Report.status == "delivered",
        ).order_by(Report.period_start.desc()).limit(3)
    )
    reports = result.scalars().all()

    if len(reports) < 2:
        return ["Insufficient report history to assess performance trend"], 0.0

    latest = reports[0]
    previous = reports[1]

    def get_metric(report: Report, key: str) -> float:
        if not report.raw_metrics_json:
            return 0.0
        try:
            raw = json.loads(report.raw_metrics_json)
            # Average the metric across all platforms
            values = []
            for platform_data in raw.values():
                if isinstance(platform_data, dict) and key in platform_data:
                    val = platform_data[key]
                    if val:
                        values.append(float(val))
            return sum(values) / len(values) if values else 0.0
        except Exception:
            return 0.0

    latest_roas = get_metric(latest, "roas")
    prev_roas = get_metric(previous, "roas")
    if prev_roas > 0 and latest_roas > 0:
        roas_change_pct = ((latest_roas - prev_roas) / prev_roas) * 100
        if roas_change_pct < -20:
            signals.append(
                f"ROAS declined {abs(roas_change_pct):.1f}% "
                f"({prev_roas:.2f}x → {latest_roas:.2f}x)"
            )
            weight += 20.0
        elif roas_change_pct < -10:
            signals.append(
                f"ROAS dipped {abs(roas_change_pct):.1f}% "
                f"({prev_roas:.2f}x → {latest_roas:.2f}x)"
            )
            weight += 10.0

    latest_ctr = get_metric(latest, "ctr")
    prev_ctr = get_metric(previous, "ctr")
    if prev_ctr > 0 and latest_ctr > 0:
        ctr_change_pct = ((latest_ctr - prev_ctr) / prev_ctr) * 100
        if ctr_change_pct < -15:
            signals.append(
                f"CTR dropped {abs(ctr_change_pct):.1f}% "
                f"({prev_ctr:.2f}% → {latest_ctr:.2f}%)"
            )
            weight += 10.0

    # 3 consecutive periods of decline = extra weight
    if len(reports) >= 3:
        oldest = reports[2]
        oldest_roas = get_metric(oldest, "roas")
        if oldest_roas > 0 and prev_roas > 0 and latest_roas > 0:
            if latest_roas < prev_roas < oldest_roas:
                signals.append("ROAS declining for 3 consecutive periods")
                weight += 10.0

    if not signals:
        signals.append("Performance metrics stable or improving")

    return signals, min(weight, 40.0)


# ── Engagement signals (from M1 communication logs) ─────────────────────────

async def get_engagement_signals(
    client_id,
    db: AsyncSession,
) -> tuple[list[str], float]:
    """
    Checks inbound message frequency and sentiment over last 30 days.
    Returns (signal_descriptions, weight_score 0-35)
    """
    from app.modules.m1_workforce.models_communication import CommunicationLog

    signals = []
    weight = 0.0

    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    # Count inbound messages last 30 days vs previous 30 days
    recent_result = await db.execute(
        select(func.count(CommunicationLog.id)).where(
            CommunicationLog.client_id == client_id,
            CommunicationLog.direction == "inbound",
            CommunicationLog.created_at >= thirty_days_ago,
        )
    )
    recent_count = recent_result.scalar() or 0

    prev_result = await db.execute(
        select(func.count(CommunicationLog.id)).where(
            CommunicationLog.client_id == client_id,
            CommunicationLog.direction == "inbound",
            CommunicationLog.created_at >= sixty_days_ago,
            CommunicationLog.created_at < thirty_days_ago,
        )
    )
    prev_count = prev_result.scalar() or 0

    if recent_count == 0 and prev_count > 0:
        signals.append("No inbound messages from client in the last 30 days")
        weight += 20.0
    elif recent_count == 0 and prev_count == 0:
        signals.append("Client has never sent an inbound message")
        weight += 5.0
    elif prev_count > 0:
        change_pct = ((recent_count - prev_count) / prev_count) * 100
        if change_pct < -50:
            signals.append(
                f"Inbound message frequency dropped {abs(change_pct):.0f}% "
                f"({prev_count} → {recent_count} messages)"
            )
            weight += 15.0

    # Days since last inbound message
    last_msg_result = await db.execute(
        select(CommunicationLog.created_at).where(
            CommunicationLog.client_id == client_id,
            CommunicationLog.direction == "inbound",
        ).order_by(CommunicationLog.created_at.desc()).limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()

    if last_msg:
        days_since = (now - last_msg).days
        if days_since > 21:
            signals.append(f"Last client message was {days_since} days ago")
            weight += 15.0
        elif days_since > 14:
            signals.append(f"No client message in {days_since} days")
            weight += 8.0

    if not signals:
        signals.append(
            f"Client engagement healthy ({recent_count} messages in last 30 days)"
        )

    return signals, min(weight, 35.0)


# ── Operational signals (from invoices and tasks) ───────────────────────────

async def get_operational_signals(
    client_id,
    agency_id,
    db: AsyncSession,
) -> tuple[list[str], float]:
    """
    Checks for overdue invoices and stalled campaign tasks.
    Returns (signal_descriptions, weight_score 0-25)
    """
    from app.modules.m2_operations.models import Invoice
    from app.modules.m1_workforce.models_task import Task

    signals = []
    weight = 0.0

    now = datetime.now(timezone.utc)

    # Overdue invoices
    overdue_result = await db.execute(
        select(func.count(Invoice.id)).where(
            Invoice.client_id == client_id,
            Invoice.status == "overdue",
        )
    )
    overdue_count = overdue_result.scalar() or 0
    if overdue_count > 0:
        signals.append(f"{overdue_count} overdue invoice(s) unpaid")
        weight += 20.0

    # Invoices sent but unpaid for more than 30 days
    late_result = await db.execute(
        select(func.count(Invoice.id)).where(
            Invoice.client_id == client_id,
            Invoice.status == "sent",
            Invoice.due_date < now,
        )
    )
    late_count = late_result.scalar() or 0
    if late_count > 0:
        signals.append(f"{late_count} invoice(s) past due date")
        weight += 5.0

    if not signals:
        signals.append("No overdue invoices — billing healthy")

    return signals, min(weight, 25.0)


# ── Compile all signals ──────────────────────────────────────────────────────

async def compile_client_signals(
    client_id,
    agency_id,
    db: AsyncSession,
) -> dict:
    """
    Runs all signal collectors for a client.
    Returns a dict with all signals and a preliminary raw score.
    """
    perf_signals, perf_weight = await get_performance_signals(client_id, db)
    eng_signals, eng_weight = await get_engagement_signals(client_id, db)
    ops_signals, ops_weight = await get_operational_signals(client_id, agency_id, db)

    raw_score = perf_weight + eng_weight + ops_weight

    return {
        "performance_signals": perf_signals,
        "engagement_signals": eng_signals,
        "operational_signals": ops_signals,
        "performance_weight": perf_weight,
        "engagement_weight": eng_weight,
        "operational_weight": ops_weight,
        "raw_score": min(raw_score, 100.0),
        "all_signals": perf_signals + eng_signals + ops_signals,
    }