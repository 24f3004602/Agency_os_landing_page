"""
M10 — Campaign Optimisation Agent

LangGraph StateGraph — six nodes:
  1. pull_live_data          — fetches live metrics from M3's ad_data utilities
  2. analyse_gaps            — compares metrics to KPI targets, finds underperformers
  3. generate_recommendations— Claude produces ranked list of changes with confidence scores
  4. get_approval            — in advisory mode: sends to AM; autonomous: auto-approves allowed types
  5. execute_changes         — executes approved changes via ad platform APIs
  6. confirm                 — logs results, sends owner notification with full change summary

In advisory mode nodes 4 and 5 are no-ops — just delivery.
In autonomous mode nodes 4 and 5 actively change live campaigns.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TypedDict

import anthropic
from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)


# ── State ────────────────────────────────────────────────────────────────────

class OptimisationState(TypedDict):
    # Inputs
    run_id: str
    agency_id: str
    client_id: str
    client_name: str
    mode: str                  # advisory | autonomous

    # Config guardrails
    max_budget_change_pct: float
    max_bid_change_pct: float
    min_daily_budget: float
    approved_change_types: list[str]
    target_roas: float | None
    target_ctr: float | None
    target_cpc: float | None

    # Performance data (populated in node 1)
    performance_data: dict

    # Analysis (populated in node 2)
    performance_gaps: list[dict]
    analysis_summary: str

    # Recommendations (populated in node 3)
    # Each: {change_type, platform, entity_id, entity_name,
    #        description, current_value, proposed_value,
    #        confidence_score, rationale}
    recommendations: list[dict]

    # Execution results (populated in nodes 4-5)
    approved_recs: list[str]    # UUIDs of approved recommendations
    executed_count: int

    errors: list[str]


# ── Node 1: Pull Live Data ────────────────────────────────────────────────────

async def pull_live_data_node(state: OptimisationState) -> OptimisationState:
    """
    Fetches last 7 days of performance data from Meta and Google Ads.
    Uses the same fetchers as M3 but with a shorter date range.
    """
    from datetime import timedelta
    from app.core.ads_data import fetch_meta_data, fetch_google_ads_data
    from app.modules.m3_reporting.models import ClientReportConfig
    from app.database import AsyncSessionLocal
    from sqlalchemy import select

    logger.info("[Optimisation] Pulling live data for %s", state["client_name"])

    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=7)

    # Fetch report config for platform credentials
    async with AsyncSessionLocal() as db:
        config_result = await db.execute(
            select(ClientReportConfig).where(
                ClientReportConfig.client_id == uuid.UUID(state["client_id"])
            )
        )
        config = config_result.scalar_one_or_none()

    meta_data = {}
    google_data = {}

    try:
        meta_data = await fetch_meta_data(
            ad_account_id=config.meta_ad_account_id if config else "",
            access_token="",
            period_start=period_start,
            period_end=now,
        )
    except Exception as e:
        logger.warning("[Optimisation] Meta fetch failed: %s", e)
        state["errors"].append(f"meta_fetch: {e}")

    try:
        google_data = await fetch_google_ads_data(
            customer_id=config.google_ads_customer_id if config else "",
            developer_token="",
            access_token="",
            period_start=period_start,
            period_end=now,
        )
    except Exception as e:
        logger.warning("[Optimisation] Google Ads fetch failed: %s", e)
        state["errors"].append(f"google_fetch: {e}")

    performance_data = {
        "period": "last_7_days",
        "period_start": period_start.isoformat(),
        "period_end": now.isoformat(),
        "meta": meta_data,
        "google_ads": google_data,
    }

    state["performance_data"] = performance_data

    # Persist snapshot to DB
    from app.database import AsyncSessionLocal
    from app.modules.m10_optimisation.models import OptimisationRun
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(OptimisationRun).where(
                OptimisationRun.id == uuid.UUID(state["run_id"])
            )
        )
        run = result.scalar_one_or_none()
        if run:
            run.performance_snapshot_json = json.dumps(performance_data)
            await db.commit()

    return state


# ── Node 2: Analyse Gaps ──────────────────────────────────────────────────────

async def analyse_gaps_node(state: OptimisationState) -> OptimisationState:
    """
    Compares live performance to KPI targets.
    Identifies underperforming platforms, campaigns, and adsets.
    Builds a structured list of performance gaps for Claude.
    """
    logger.info("[Optimisation] Analysing gaps for %s", state["client_name"])

    gaps = []

    def check_gap(platform: str, metric: str, current: float, target: float | None, lower_is_better: bool = False):
        if target is None or current == 0:
            return
        if lower_is_better:
            gap_pct = (current - target) / target * 100
            is_gap = current > target
        else:
            gap_pct = (target - current) / target * 100
            is_gap = current < target

        if is_gap and abs(gap_pct) > 5:  # only flag gaps > 5%
            gaps.append({
                "platform": platform,
                "metric": metric,
                "current": round(current, 2),
                "target": target,
                "gap_pct": round(gap_pct, 1),
                "severity": "critical" if abs(gap_pct) > 25 else "warning",
            })

    meta = state["performance_data"].get("meta", {})
    google = state["performance_data"].get("google_ads", {})

    check_gap("meta", "roas", meta.get("roas", 0), state.get("target_roas"))
    check_gap("meta", "ctr", meta.get("ctr", 0), state.get("target_ctr"))
    check_gap("meta", "cpc", meta.get("cpc", 0), state.get("target_cpc"), lower_is_better=True)

    check_gap("google_ads", "roas", google.get("roas", 0), state.get("target_roas"))
    check_gap("google_ads", "ctr", google.get("ctr", 0), state.get("target_ctr"))
    check_gap("google_ads", "cpc", google.get("cpc", 0), state.get("target_cpc"), lower_is_better=True)

    state["performance_gaps"] = gaps

    # Build summary text
    if gaps:
        gap_lines = [
            f"- {g['platform'].upper()} {g['metric'].upper()}: "
            f"{g['current']} vs target {g['target']} "
            f"({g['gap_pct']:+.1f}%) [{g['severity']}]"
            for g in gaps
        ]
        state["analysis_summary"] = (
            f"{len(gaps)} performance gap(s) detected:\n"
            + "\n".join(gap_lines)
        )
    else:
        state["analysis_summary"] = (
            "All KPIs within target range. No critical gaps detected."
        )

    logger.info(
        "[Optimisation] Found %d gap(s) for %s",
        len(gaps),
        state["client_name"],
    )
    return state


# ── Node 3: Generate Recommendations ─────────────────────────────────────────

async def generate_recommendations_node(state: OptimisationState) -> OptimisationState:
    """
    Claude produces a ranked list of specific actionable changes.
    Each recommendation has: change_type, platform, entity details,
    confidence score (0-100), and plain-English rationale.
    """
    from app.config import settings

    logger.info(
        "[Optimisation] Generating recommendations for %s",
        state["client_name"],
    )

    if not settings.anthropic_api_key:
        state["recommendations"] = _stub_recommendations(state)
        return state

    meta = state["performance_data"].get("meta", {})
    google = state["performance_data"].get("google_ads", {})

    gaps_text = state["analysis_summary"]

    meta_summary = (
        f"Spend: ₹{meta.get('spend', 0):,.0f} | "
        f"ROAS: {meta.get('roas', 0):.2f}x | "
        f"CTR: {meta.get('ctr', 0):.2f}% | "
        f"CPC: ₹{meta.get('cpc', 0):.2f} | "
        f"Conversions: {meta.get('conversions', 0)}"
    )

    google_summary = (
        f"Spend: ₹{google.get('spend', 0):,.0f} | "
        f"ROAS: {google.get('roas', 0):.2f}x | "
        f"CTR: {google.get('ctr', 0):.2f}% | "
        f"CPC: ₹{google.get('cpc', 0):.2f} | "
        f"Conversions: {google.get('conversions', 0)}"
    )

    targets_text = (
        f"Target ROAS: {state['target_roas'] or 'not set'} | "
        f"Target CTR: {state['target_ctr'] or 'not set'}% | "
        f"Target CPC: ₹{state['target_cpc'] or 'not set'}"
    )

    prompt = f"""You are a senior paid media strategist reviewing campaign performance.

CLIENT: {state["client_name"]}
PERIOD: Last 7 days

META ADS PERFORMANCE:
{meta_summary}

GOOGLE ADS PERFORMANCE:
{google_summary}

KPI TARGETS:
{targets_text}

PERFORMANCE GAPS:
{gaps_text}

Generate specific, actionable optimisation recommendations.
Each recommendation must be something that can actually be executed via an ad platform API.

Valid change types:
- pause_ad         : pause a specific underperforming ad
- pause_adset      : pause an entire underperforming adset
- adjust_bid       : change bid for a campaign or adset
- reallocate_budget: move budget from underperforming to performing platform/campaign
- scale_budget     : increase budget on a high-performing campaign
- change_creative  : flag for new creative (cannot be automated — advisory only)

Respond with a JSON array of 3-5 recommendations. Each:
{{
  "change_type": "<type from list above>",
  "platform": "meta|google_ads",
  "entity_id": "<use realistic placeholder IDs like 'meta_adset_001'>",
  "entity_name": "<descriptive name like 'Retargeting - 30 day LAL'>",
  "description": "<plain English: what changes and by how much>",
  "current_value": "<current metric value>",
  "proposed_value": "<what it would be changed to>",
  "confidence_score": <0-100>,
  "rationale": "<one sentence: why this change will improve performance>"
}}

Sort by confidence_score descending (highest confidence first).
Return ONLY the JSON array, no other text."""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        recommendations = json.loads(raw)
        state["recommendations"] = recommendations

        logger.info(
            "[Optimisation] Generated %d recommendation(s) for %s",
            len(recommendations),
            state["client_name"],
        )

    except Exception as e:
        logger.error("[Optimisation] Recommendation generation failed: %s", e)
        state["errors"].append(f"generate_recommendations: {e}")
        state["recommendations"] = _stub_recommendations(state)

    # Persist recommendations to DB
    from app.database import AsyncSessionLocal
    from app.modules.m10_optimisation.models import OptimisationRun, OptimisationRecommendation
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        run_result = await db.execute(
            select(OptimisationRun).where(
                OptimisationRun.id == uuid.UUID(state["run_id"])
            )
        )
        run = run_result.scalar_one_or_none()

        if run:
            for rec_data in state["recommendations"]:
                rec = OptimisationRecommendation(
                    run_id=run.id,
                    agency_id=uuid.UUID(state["agency_id"]),
                    change_type=rec_data.get("change_type", "other"),
                    platform=rec_data.get("platform", "meta"),
                    entity_id=rec_data.get("entity_id"),
                    entity_name=rec_data.get("entity_name"),
                    description=rec_data.get("description", ""),
                    current_value=rec_data.get("current_value"),
                    proposed_value=rec_data.get("proposed_value"),
                    confidence_score=float(rec_data.get("confidence_score", 0)),
                    rationale=rec_data.get("rationale"),
                    status="pending",
                )
                db.add(rec)

            run.total_recommendations = len(state["recommendations"])
            run.analysis_summary = state["analysis_summary"]
            run.status = "recommendations_ready"

        await db.commit()

    return state


def _stub_recommendations(state: OptimisationState) -> list[dict]:
    """Fallback when Claude unavailable."""
    return [
        {
            "change_type": "pause_ad",
            "platform": "meta",
            "entity_id": "meta_ad_001",
            "entity_name": "Awareness - Static Image v3",
            "description": "Pause this ad — CTR 0.4% vs 2% target, burning budget with no conversions",
            "current_value": "CTR: 0.4%, Spend: ₹8,500",
            "proposed_value": "Ad paused — budget reallocated",
            "confidence_score": 85.0,
            "rationale": "Extremely low CTR relative to campaign average suggests creative fatigue",
        },
        {
            "change_type": "reallocate_budget",
            "platform": "meta",
            "entity_id": "meta_adset_002",
            "entity_name": "Retargeting - 30 Day",
            "description": "Increase retargeting budget by ₹2,000/day — ROAS 4.8x, underspending",
            "current_value": "₹3,000/day",
            "proposed_value": "₹5,000/day",
            "confidence_score": 78.0,
            "rationale": "Best performing adset is budget-constrained — scaling will improve overall ROAS",
        },
        {
            "change_type": "adjust_bid",
            "platform": "google_ads",
            "entity_id": "google_campaign_001",
            "entity_name": "Brand Keywords - Exact",
            "description": "Reduce target CPA bid from ₹250 to ₹200 — current CPA ₹180, room to tighten",
            "current_value": "Target CPA: ₹250",
            "proposed_value": "Target CPA: ₹200",
            "confidence_score": 65.0,
            "rationale": "Actual CPA well below target — reducing bid will improve efficiency without losing volume",
        },
    ]


# ── Node 4: Get Approval ─────────────────────────────────────────────────────

async def get_approval_node(state: OptimisationState) -> OptimisationState:
    """
    Advisory mode: sends recommendations to AM via Slack, no execution.
    Autonomous mode: auto-approves recommendations whose change_type
    is in the client's approved_change_types list.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m10_optimisation.models import OptimisationRun, OptimisationRecommendation
    from sqlalchemy import select

    logger.info(
        "[Optimisation] Processing approval for %s (mode=%s)",
        state["client_name"],
        state["mode"],
    )

    approved_ids = []

    async with AsyncSessionLocal() as db:
        # Fetch recommendations for this run
        recs_result = await db.execute(
            select(OptimisationRecommendation).where(
                OptimisationRecommendation.run_id == uuid.UUID(state["run_id"])
            )
        )
        recs = recs_result.scalars().all()

        if state["mode"] == "autonomous":
            for rec in recs:
                if rec.change_type in state["approved_change_types"]:
                    rec.status = "approved"
                    approved_ids.append(str(rec.id))
                    logger.info(
                        "[Optimisation] Auto-approved: %s (%s)",
                        rec.change_type,
                        rec.entity_name,
                    )
                else:
                    # Not in approved types — falls back to advisory
                    rec.status = "pending"

        # Update run
        run_result = await db.execute(
            select(OptimisationRun).where(
                OptimisationRun.id == uuid.UUID(state["run_id"])
            )
        )
        run = run_result.scalar_one_or_none()
        if run:
            run.approved_count = len(approved_ids)
            if approved_ids:
                run.status = "approved"

        await db.commit()

    state["approved_recs"] = approved_ids

    # Send advisory notification regardless of mode
    recs_text = "\n".join(
        f"  {i+1}. [{r.get('change_type', '').upper()}] "
        f"{r.get('entity_name', '')} — "
        f"{r.get('description', '')[:80]} "
        f"(confidence: {r.get('confidence_score', 0):.0f}%)"
        for i, r in enumerate(state["recommendations"])
    )

    mode_text = (
        f"Autonomous mode: {len(approved_ids)} change(s) will execute automatically."
        if state["mode"] == "autonomous"
        else "Advisory mode: Please review and approve in the platform."
    )

    logger.warning(
        "[SLACK STUB] Optimisation recommendations for %s:\n%s\n\n%s",
        state["client_name"],
        recs_text,
        mode_text,
    )

    return state


# ── Node 5: Execute Changes ───────────────────────────────────────────────────

async def execute_changes_node(state: OptimisationState) -> OptimisationState:
    """
    Advisory mode: no-op — recommendations already delivered.
    Autonomous mode: executes approved recommendations via ad APIs.
    Records execution result on each recommendation row.
    """
    if state["mode"] != "autonomous" or not state["approved_recs"]:
        state["executed_count"] = 0
        return state

    from app.database import AsyncSessionLocal
    from app.modules.m10_optimisation.models import OptimisationRecommendation
    from app.core.ad_execution import (
        meta_pause_ad,
        meta_update_adset_budget,
        google_pause_ad,
        validate_budget_change,
    )
    from sqlalchemy import select

    logger.info(
        "[Optimisation] Executing %d approved change(s) for %s",
        len(state["approved_recs"]),
        state["client_name"],
    )

    executed = 0
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        for rec_id in state["approved_recs"]:
            rec_result = await db.execute(
                select(OptimisationRecommendation).where(
                    OptimisationRecommendation.id == uuid.UUID(rec_id)
                )
            )
            rec = rec_result.scalar_one_or_none()
            if not rec:
                continue

            rec.status = "executing"
            await db.commit()

            result = {}

            try:
                if rec.platform == "meta":
                    if rec.change_type == "pause_ad":
                        result = await meta_pause_ad(
                            ad_id=rec.entity_id or "",
                            access_token="",  # TODO: fetch stored token
                        )
                    elif rec.change_type in ("reallocate_budget", "scale_budget"):
                        # Parse proposed budget from proposed_value
                        # e.g. "₹5,000/day" → 500000 cents
                        try:
                            budget_str = (rec.proposed_value or "").replace("₹", "").replace(",", "").split("/")[0].strip()
                            budget_inr = float(budget_str)
                            current_str = (rec.current_value or "").replace("₹", "").replace(",", "").split("/")[0].strip()
                            current_inr = float(current_str) if current_str else 0

                            valid, reason = validate_budget_change(
                                current_budget=current_inr,
                                proposed_budget=budget_inr,
                                max_change_pct=state["max_budget_change_pct"],
                                min_daily_budget=state["min_daily_budget"],
                            )

                            if valid:
                                # Meta expects daily budget in cents (paise for INR)
                                result = await meta_update_adset_budget(
                                    adset_id=rec.entity_id or "",
                                    daily_budget_cents=int(budget_inr * 100),
                                    access_token="",
                                )
                            else:
                                result = {"status": "blocked", "reason": reason}
                                logger.warning(
                                    "[Optimisation] Guardrail blocked: %s", reason
                                )
                        except (ValueError, AttributeError) as e:
                            result = {"status": "parse_error", "error": str(e)}

                elif rec.platform == "google_ads":
                    if rec.change_type == "pause_ad":
                        result = await google_pause_ad(
                            customer_id="",
                            ad_group_ad_resource=rec.entity_id or "",
                            developer_token="",
                            access_token="",
                        )

                rec.status = "executed"
                rec.executed_at = now
                rec.execution_result = json.dumps(result)
                executed += 1

            except Exception as e:
                logger.error(
                    "[Optimisation] Execution failed for rec %s: %s",
                    rec_id, e,
                )
                rec.status = "failed"
                rec.execution_result = json.dumps({"error": str(e)})

            await db.commit()

    state["executed_count"] = executed
    return state


# ── Node 6: Confirm ───────────────────────────────────────────────────────────

async def confirm_node(state: OptimisationState) -> OptimisationState:
    """
    Updates run to complete status.
    Sends owner notification with execution summary.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m10_optimisation.models import OptimisationRun
    from sqlalchemy import select

    logger.info("[Optimisation] Confirming run for %s", state["client_name"])

    async with AsyncSessionLocal() as db:
        run_result = await db.execute(
            select(OptimisationRun).where(
                OptimisationRun.id == uuid.UUID(state["run_id"])
            )
        )
        run = run_result.scalar_one_or_none()
        if run:
            run.status = "complete"
            run.executed_count = state["executed_count"]
            await db.commit()

    if state["mode"] == "autonomous" and state["executed_count"] > 0:
        logger.warning(
            "[SLACK STUB] ✅ Autonomous optimisation complete for %s: "
            "%d change(s) executed. Review in platform.",
            state["client_name"],
            state["executed_count"],
        )

    return state


# ── Build Graph ──────────────────────────────────────────────────────────────

def build_optimisation_graph() -> StateGraph:
    graph = StateGraph(OptimisationState)

    graph.add_node("pull_live_data", pull_live_data_node)
    graph.add_node("analyse_gaps", analyse_gaps_node)
    graph.add_node("generate_recommendations", generate_recommendations_node)
    graph.add_node("get_approval", get_approval_node)
    graph.add_node("execute_changes", execute_changes_node)
    graph.add_node("confirm", confirm_node)

    graph.set_entry_point("pull_live_data")
    graph.add_edge("pull_live_data", "analyse_gaps")
    graph.add_edge("analyse_gaps", "generate_recommendations")
    graph.add_edge("generate_recommendations", "get_approval")
    graph.add_edge("get_approval", "execute_changes")
    graph.add_edge("execute_changes", "confirm")
    graph.add_edge("confirm", END)

    return graph.compile()


# ── Trajectory Analysis (separate from optimisation) ─────────────────────────

async def run_trajectory_analysis(
    client_id: str,
    agency_id: str,
    client_name: str,
    target_roas: float | None,
    target_ctr: float | None,
) -> list[dict]:
    """
    Projects end-of-month performance based on current trajectory.
    Returns list of alert dicts for any KPIs predicted to miss target.
    Not a LangGraph — simple mathematical projection + Claude action suggestion.
    """
    from datetime import timedelta
    import calendar

    now = datetime.now(timezone.utc)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day_of_month = now.day
    days_remaining = days_in_month - day_of_month

    if days_remaining <= 0:
        return []

    # Fetch last 7 days performance
    from app.core.ads_data import fetch_meta_data

    period_start = now - timedelta(days=7)
    meta_data = await fetch_meta_data(
        ad_account_id="",
        access_token="",
        period_start=period_start,
        period_end=now,
    )

    alerts = []

    def project_eom(current_7day_avg: float) -> float:
        """Simple linear projection."""
        daily_avg = current_7day_avg / 7
        return daily_avg * days_in_month

    # ROAS projection
    if target_roas and meta_data.get("roas", 0) > 0:
        current_roas = meta_data["roas"]
        projected_eom_roas = current_roas  # ROAS doesn't compound — use current rate

        if projected_eom_roas < target_roas:
            gap_pct = (target_roas - projected_eom_roas) / target_roas * 100
            alerts.append({
                "kpi_name": "roas",
                "current_value": current_roas,
                "target_value": target_roas,
                "projected_eom_value": projected_eom_roas,
                "gap_percentage": round(gap_pct, 1),
                "severity": "critical" if gap_pct > 25 else "warning",
                "days_remaining": days_remaining,
            })

    return alerts


# ── Runners ──────────────────────────────────────────────────────────────────

async def run_optimisation_agent(
    run_id: str,
    agency_id: str,
    client_id: str,
    client_name: str,
    mode: str,
    max_budget_change_pct: float = 20.0,
    max_bid_change_pct: float = 15.0,
    min_daily_budget: float = 500.0,
    approved_change_types: list[str] | None = None,
    target_roas: float | None = None,
    target_ctr: float | None = None,
    target_cpc: float | None = None,
) -> dict:
    graph = build_optimisation_graph()

    initial_state: OptimisationState = {
        "run_id": run_id,
        "agency_id": agency_id,
        "client_id": client_id,
        "client_name": client_name,
        "mode": mode,
        "max_budget_change_pct": max_budget_change_pct,
        "max_bid_change_pct": max_bid_change_pct,
        "min_daily_budget": min_daily_budget,
        "approved_change_types": approved_change_types or ["pause_ad"],
        "target_roas": target_roas,
        "target_ctr": target_ctr,
        "target_cpc": target_cpc,
        "performance_data": {},
        "performance_gaps": [],
        "analysis_summary": "",
        "recommendations": [],
        "approved_recs": [],
        "executed_count": 0,
        "errors": [],
    }

    return await graph.ainvoke(initial_state)