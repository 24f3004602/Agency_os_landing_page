"""
M4 — Churn Prevention Agent

LangGraph StateGraph — five nodes:
  1. fetch_signals       — collects performance, engagement, ops signals
  2. score_risk          — Claude evaluates signals and produces 0-100 score
  3. enrich_with_research— pulls competitor context from M6 if active
  4. generate_alert      — writes ChurnAlert to DB with retention actions
  5. notify              — Slack alert to owner with risk summary

Only creates an alert if risk_score >= threshold (default 40).
Runs per-client — the Celery job calls this for every active client.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TypedDict

import anthropic
from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)

ALERT_THRESHOLD = 40.0   # create alert if score >= this


# ── State ────────────────────────────────────────────────────────────────────

class ChurnState(TypedDict):
    # Inputs
    client_id: str
    client_name: str
    agency_id: str
    is_m6_active: bool   # whether Research Agent module is active

    # Signal data
    signals: dict           # output of compile_client_signals
    risk_score: float       # 0-100
    trigger_reasons: list[str]
    retention_actions: list[str]
    competitor_context: str | None

    # Control
    should_alert: bool
    alert_id: str | None
    errors: list[str]


# ── Node 1: Fetch Signals ────────────────────────────────────────────────────

async def fetch_signals_node(state: ChurnState) -> ChurnState:
    """Collects all risk signals for the client."""
    from app.core.churn_signals import compile_client_signals
    from app.database import AsyncSessionLocal

    logger.info("[Churn] Fetching signals for %s", state["client_name"])

    try:
        async with AsyncSessionLocal() as db:
            signals = await compile_client_signals(
                client_id=uuid.UUID(state["client_id"]),
                agency_id=uuid.UUID(state["agency_id"]),
                db=db,
            )
        state["signals"] = signals
    except Exception as e:
        logger.error("[Churn] Signal fetch failed for %s: %s", state["client_name"], e)
        state["errors"].append(f"fetch_signals: {e}")
        state["signals"] = {"raw_score": 0.0, "all_signals": []}

    return state


# ── Node 2: Score Risk ───────────────────────────────────────────────────────

async def score_risk_node(state: ChurnState) -> ChurnState:
    """
    Claude evaluates the compiled signals and produces:
    - A precise risk score 0-100
    - The top trigger reasons (most impactful signals)
    - Concrete retention actions tailored to this client's signals
    """
    from app.config import settings

    logger.info("[Churn] Scoring risk for %s", state["client_name"])

    signals = state["signals"]

    if not settings.anthropic_api_key:
        # Fall back to raw score if no API key
        state["risk_score"] = signals.get("raw_score", 0.0)
        state["trigger_reasons"] = signals.get("all_signals", [])[:3]
        state["retention_actions"] = ["Review account status with client"]
        return state

    signals_text = f"""
Performance Signals (weight {signals.get('performance_weight', 0):.1f}/40):
{chr(10).join('- ' + s for s in signals.get('performance_signals', []))}

Engagement Signals (weight {signals.get('engagement_weight', 0):.1f}/35):
{chr(10).join('- ' + s for s in signals.get('engagement_signals', []))}

Operational Signals (weight {signals.get('operational_weight', 0):.1f}/25):
{chr(10).join('- ' + s for s in signals.get('operational_signals', []))}

Raw algorithmic score: {signals.get('raw_score', 0):.1f}/100
"""

    prompt = f"""You are a client success analyst at a digital marketing agency.
Evaluate the churn risk for this client based on the signals below.

Client: {state["client_name"]}

SIGNALS:
{signals_text}

Respond ONLY in this exact JSON format with no other text:
{{
  "risk_score": <integer 0-100>,
  "score_rationale": "<one sentence explaining the score>",
  "top_triggers": [
    "<most critical signal>",
    "<second most critical>",
    "<third most critical>"
  ],
  "retention_actions": [
    "<specific action 1 — what to do this week>",
    "<specific action 2 — medium term>",
    "<specific action 3 — relationship repair if needed>"
  ]
}}

Scoring guide:
  0-20   : Low risk — client is happy and engaged
  21-40  : Watch — some weak signals, monitor closely
  41-60  : At risk — action needed within 2 weeks
  61-80  : High risk — urgent intervention needed
  81-100 : Critical — likely churning, escalate immediately"""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(response.content[0].text.strip())

        state["risk_score"] = float(result.get("risk_score", 0))
        state["trigger_reasons"] = result.get("top_triggers", [])
        state["retention_actions"] = result.get("retention_actions", [])

        logger.info(
            "[Churn] %s scored %.1f/100 — %s",
            state["client_name"],
            state["risk_score"],
            result.get("score_rationale", ""),
        )

    except Exception as e:
        logger.error("[Churn] Scoring failed for %s: %s", state["client_name"], e)
        state["errors"].append(f"score_risk: {e}")
        state["risk_score"] = signals.get("raw_score", 0.0)
        state["trigger_reasons"] = signals.get("all_signals", [])[:3]
        state["retention_actions"] = ["Manually review this client's account"]

    state["should_alert"] = state["risk_score"] >= ALERT_THRESHOLD
    return state


# ── Node 3: Enrich with Research ─────────────────────────────────────────────

async def enrich_with_research_node(state: ChurnState) -> ChurnState:
    """
    If M6 (Research Agent) is active, pulls competitor intelligence
    to add context to the alert.
    e.g. "Competitor increased Meta spend 40% this month"
    """
    if not state["is_m6_active"] or not state["should_alert"]:
        state["competitor_context"] = None
        return state

    logger.info("[Churn] Enriching with M6 research for %s", state["client_name"])

    # M6 research briefs are stored in Qdrant (vector store)
    # For now stub — full Qdrant retrieval built in M6 (Phase 9)
    # TODO Phase 9: query Qdrant for recent competitor briefs for this client
    state["competitor_context"] = None

    return state


# ── Node 4: Generate Alert ───────────────────────────────────────────────────

async def generate_alert_node(state: ChurnState) -> ChurnState:
    """
    Creates a ChurnAlert record in the DB.
    Only runs if risk_score >= ALERT_THRESHOLD.
    """
    if not state["should_alert"]:
        logger.info(
            "[Churn] %s score %.1f below threshold — no alert",
            state["client_name"],
            state["risk_score"],
        )
        return state

    from app.database import AsyncSessionLocal
    from app.modules.m4_churn.models import ChurnAlert

    logger.info(
        "[Churn] Creating alert for %s (score=%.1f)",
        state["client_name"],
        state["risk_score"],
    )

    try:
        async with AsyncSessionLocal() as db:
            alert = ChurnAlert(
                agency_id=uuid.UUID(state["agency_id"]),
                client_id=uuid.UUID(state["client_id"]),
                risk_score=state["risk_score"],
                trigger_reasons_json=json.dumps(state["trigger_reasons"]),
                retention_actions_json=json.dumps(state["retention_actions"]),
                competitor_context=state["competitor_context"],
                status="open",
            )
            db.add(alert)
            await db.commit()
            await db.refresh(alert)
            state["alert_id"] = str(alert.id)

            # Also update client status to at_risk
            from app.modules.people_and_tenant.users.models import Client
            from sqlalchemy import select
            client_result = await db.execute(
                select(Client).where(Client.id == uuid.UUID(state["client_id"]))
            )
            client = client_result.scalar_one_or_none()
            if client and client.status == "active":
                client.status = "at_risk"
                await db.commit()

    except Exception as e:
        logger.error("[Churn] Alert creation failed: %s", e)
        state["errors"].append(f"generate_alert: {e}")

    return state


# ── Node 5: Notify ───────────────────────────────────────────────────────────

async def notify_node(state: ChurnState) -> ChurnState:
    """
    Sends Slack alert to owner with risk score, triggers, and actions.
    Stub until Slack SDK wired in dashboard phase.
    """
    if not state["should_alert"]:
        return state

    score = state["risk_score"]
    emoji = "🟡" if score < 60 else "🔴" if score < 80 else "🚨"

    triggers_text = "\n".join(f"  • {t}" for t in state["trigger_reasons"])
    actions_text = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(state["retention_actions"]))

    slack_message = (
        f"{emoji} *Churn Risk Alert — {state['client_name']}*\n"
        f"Risk Score: *{score:.0f}/100*\n\n"
        f"*Why:*\n{triggers_text}\n\n"
        f"*Recommended Actions:*\n{actions_text}"
    )

    if state.get("competitor_context"):
        slack_message += f"\n\n*Competitor Context:*\n{state['competitor_context']}"

    # TODO: replace with Slack SDK call
    logger.warning("[SLACK STUB] Churn alert:\n%s", slack_message)

    return state


# ── Build graph ──────────────────────────────────────────────────────────────

def build_churn_graph() -> StateGraph:
    graph = StateGraph(ChurnState)

    graph.add_node("fetch_signals", fetch_signals_node)
    graph.add_node("score_risk", score_risk_node)
    graph.add_node("enrich_with_research", enrich_with_research_node)
    graph.add_node("generate_alert", generate_alert_node)
    graph.add_node("notify", notify_node)

    graph.set_entry_point("fetch_signals")
    graph.add_edge("fetch_signals", "score_risk")
    graph.add_edge("score_risk", "enrich_with_research")
    graph.add_edge("enrich_with_research", "generate_alert")
    graph.add_edge("generate_alert", "notify")
    graph.add_edge("notify", END)

    return graph.compile()


# ── Runner ───────────────────────────────────────────────────────────────────

async def run_churn_agent(
    client_id: str,
    client_name: str,
    agency_id: str,
    is_m6_active: bool = False,
) -> dict:
    graph = build_churn_graph()

    initial_state: ChurnState = {
        "client_id": client_id,
        "client_name": client_name,
        "agency_id": agency_id,
        "is_m6_active": is_m6_active,
        "signals": {},
        "risk_score": 0.0,
        "trigger_reasons": [],
        "retention_actions": [],
        "competitor_context": None,
        "should_alert": False,
        "alert_id": None,
        "errors": [],
    }

    return await graph.ainvoke(initial_state)