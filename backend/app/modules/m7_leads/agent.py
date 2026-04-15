"""
M7 — Lead Analyst Agent

LangGraph StateGraph — six nodes:
  1. intake_lead        — validates and normalises lead data
  2. fetch_context      — pulls ICP profile from DB
  3. score_against_icp  — Claude evaluates lead vs ICP, produces 0-100 score
  4. write_back_hubspot — writes score to HubSpot deal/contact if IDs present
  5. create_task        — creates follow-up task assigned to AE in platform DB
  6. notify             — Slack notification to owner with score summary

Score categories:
  80-100 : Hot lead — immediate outreach recommended
  60-79  : Warm lead — follow up within 48h
  40-59  : Lukewarm — nurture, not priority
  0-39   : Poor fit — likely disqualify
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

class LeadState(TypedDict):
    # Inputs
    lead_id: str
    agency_id: str

    # Lead data (populated from DB in intake node)
    full_name: str
    email: str
    company_name: str
    company_size: str | None
    industry: str | None
    monthly_ad_budget: str | None
    designation: str | None
    pain_points: str | None
    website: str | None
    source: str
    hubspot_deal_id: str | None
    hubspot_contact_id: str | None
    assigned_to_id: str | None

    # ICP data (populated from DB in fetch_context node)
    icp_ideal_industries: str
    icp_company_size: str
    icp_ad_budget: str
    icp_decision_maker: str
    icp_pain_points: str
    icp_disqualifiers: str
    icp_high_priority_threshold: int

    # Scoring outputs
    score: float
    rationale: str
    strengths: list[str]
    concerns: list[str]
    next_action: str

    errors: list[str]


# ── Node 1: Intake Lead ──────────────────────────────────────────────────────

async def intake_lead_node(state: LeadState) -> LeadState:
    """
    Loads the lead from the DB and populates state fields.
    Validates required fields exist before proceeding.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m7_leads.models import Lead
    from sqlalchemy import select

    logger.info("[Lead] Intaking lead %s", state["lead_id"])

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Lead).where(Lead.id == uuid.UUID(state["lead_id"]))
        )
        lead = result.scalar_one_or_none()

        if not lead:
            state["errors"].append("Lead not found in DB")
            return state

        state["full_name"] = lead.full_name
        state["email"] = lead.email
        state["company_name"] = lead.company_name
        state["company_size"] = lead.company_size
        state["industry"] = lead.industry
        state["monthly_ad_budget"] = lead.monthly_ad_budget
        state["designation"] = lead.designation
        state["pain_points"] = lead.pain_points
        state["website"] = lead.website
        state["source"] = lead.source
        state["hubspot_deal_id"] = lead.hubspot_deal_id
        state["hubspot_contact_id"] = lead.hubspot_contact_id
        state["assigned_to_id"] = (
            str(lead.assigned_to) if lead.assigned_to else None
        )

    logger.info(
        "[Lead] Loaded: %s at %s",
        state["full_name"],
        state["company_name"],
    )
    return state


# ── Node 2: Fetch Context ────────────────────────────────────────────────────

async def fetch_context_node(state: LeadState) -> LeadState:
    """
    Loads the agency's ICP profile from DB.
    Uses defaults if no ICP has been defined.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m7_leads.models import IcpProfile
    from sqlalchemy import select

    logger.info("[Lead] Fetching ICP for agency %s", state["agency_id"])

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(IcpProfile).where(
                IcpProfile.agency_id == uuid.UUID(state["agency_id"])
            )
        )
        icp = result.scalar_one_or_none()

        if icp:
            state["icp_ideal_industries"] = icp.ideal_industries
            state["icp_company_size"] = icp.ideal_company_size
            state["icp_ad_budget"] = icp.ideal_ad_budget
            state["icp_decision_maker"] = icp.ideal_decision_maker
            state["icp_pain_points"] = icp.ideal_pain_points
            state["icp_disqualifiers"] = icp.disqualifiers
            state["icp_high_priority_threshold"] = icp.high_priority_threshold
        else:
            # Sensible defaults if no ICP defined
            state["icp_ideal_industries"] = "D2C brands, e-commerce, retail"
            state["icp_company_size"] = "10-500 employees"
            state["icp_ad_budget"] = "Monthly spend ₹2L to ₹50L"
            state["icp_decision_maker"] = "Founder, CMO, Marketing Head"
            state["icp_pain_points"] = "Struggling with ROAS, want to scale paid ads"
            state["icp_disqualifiers"] = "Budget under ₹1L/month, no marketing budget"
            state["icp_high_priority_threshold"] = 70
            logger.warning(
                "[Lead] No ICP profile found for agency %s — using defaults",
                state["agency_id"],
            )

    return state


# ── Node 3: Score Against ICP ─────────────────────────────────────────────────

async def score_against_icp_node(state: LeadState) -> LeadState:
    """
    Claude evaluates the lead against the ICP and produces:
    - score (0-100)
    - rationale (why this score)
    - strengths (what fits the ICP)
    - concerns (what doesn't fit)
    - next_action (what the AE should do)
    """
    from app.config import settings

    logger.info(
        "[Lead] Scoring %s at %s",
        state["full_name"],
        state["company_name"],
    )

    if not settings.anthropic_api_key:
        state["score"] = 50.0
        state["rationale"] = "Scored at 50 (neutral) — ANTHROPIC_API_KEY not configured."
        state["strengths"] = ["Unable to assess without AI"]
        state["concerns"] = ["Set ANTHROPIC_API_KEY for real scoring"]
        state["next_action"] = "Manually review this lead"
        return state

    prompt = f"""You are a lead qualification specialist at a digital marketing agency.

Score this incoming lead against the agency's Ideal Client Profile (ICP).

LEAD INFORMATION:
Name: {state["full_name"]}
Title/Designation: {state["designation"] or "Not provided"}
Company: {state["company_name"]}
Industry: {state["industry"] or "Not provided"}
Company Size: {state["company_size"] or "Not provided"}
Monthly Ad Budget: {state["monthly_ad_budget"] or "Not provided"}
Website: {state["website"] or "Not provided"}
Pain Points: {state["pain_points"] or "Not provided"}
Source: {state["source"]}

AGENCY ICP:
Ideal Industries: {state["icp_ideal_industries"]}
Ideal Company Size: {state["icp_company_size"]}
Ideal Ad Budget: {state["icp_ad_budget"]}
Ideal Decision Maker: {state["icp_decision_maker"]}
Ideal Pain Points: {state["icp_pain_points"]}
Disqualifiers: {state["icp_disqualifiers"]}

Score this lead 0-100 based on how well they match the ICP.

Scoring guide:
  80-100 : Excellent fit — hot lead, prioritise immediately
  60-79  : Good fit — warm lead, follow up within 48 hours
  40-59  : Partial fit — lukewarm, nurture over time
  20-39  : Poor fit — likely not a good client
  0-19   : Clear disqualifier — politely decline

Respond ONLY in this exact JSON format with no other text:
{{
  "score": <integer 0-100>,
  "rationale": "<2-3 sentences explaining the score>",
  "strengths": [
    "<specific reason this lead fits>",
    "<another fit reason>"
  ],
  "concerns": [
    "<specific concern or gap>",
    "<another concern if any>"
  ],
  "next_action": "<one specific action the account executive should take this week>"
}}"""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(response.content[0].text.strip())

        state["score"] = float(result.get("score", 50))
        state["rationale"] = result.get("rationale", "")
        state["strengths"] = result.get("strengths", [])
        state["concerns"] = result.get("concerns", [])
        state["next_action"] = result.get("next_action", "Review and contact")

        logger.info(
            "[Lead] %s scored %.0f/100",
            state["company_name"],
            state["score"],
        )

    except Exception as e:
        logger.error("[Lead] Scoring failed: %s", e)
        state["errors"].append(f"score_against_icp: {e}")
        state["score"] = 50.0
        state["rationale"] = f"Scoring failed: {e}"
        state["strengths"] = []
        state["concerns"] = []
        state["next_action"] = "Manually review this lead"

    # Persist score to DB
    from app.database import AsyncSessionLocal
    from app.modules.m7_leads.models import Lead, LeadScore
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Upsert LeadScore
        score_result = await db.execute(
            select(LeadScore).where(
                LeadScore.lead_id == uuid.UUID(state["lead_id"])
            )
        )
        lead_score = score_result.scalar_one_or_none()

        if lead_score:
            lead_score.score = state["score"]
            lead_score.rationale = state["rationale"]
            lead_score.strengths_json = json.dumps(state["strengths"])
            lead_score.concerns_json = json.dumps(state["concerns"])
            lead_score.next_action = state["next_action"]
        else:
            lead_score = LeadScore(
                lead_id=uuid.UUID(state["lead_id"]),
                score=state["score"],
                rationale=state["rationale"],
                strengths_json=json.dumps(state["strengths"]),
                concerns_json=json.dumps(state["concerns"]),
                next_action=state["next_action"],
            )
            db.add(lead_score)

        # Update lead status
        lead_result = await db.execute(
            select(Lead).where(Lead.id == uuid.UUID(state["lead_id"]))
        )
        lead = lead_result.scalar_one_or_none()
        if lead:
            lead.status = "scored"

        await db.commit()

    return state


# ── Node 4: Write Back to HubSpot ────────────────────────────────────────────

async def write_back_hubspot_node(state: LeadState) -> LeadState:
    """
    Writes the ICP score and rationale back to HubSpot
    as custom contact/deal properties.

    Requires:
      - HUBSPOT_ACCESS_TOKEN in .env
      - Custom property "icp_score" created in HubSpot
    """
    from app.core.hubspot import (
        update_contact_property,
        update_deal_property,
    )
    from app.database import AsyncSessionLocal
    from app.modules.m7_leads.models import LeadScore
    from sqlalchemy import select

    logger.info("[Lead] Writing back to HubSpot for %s", state["company_name"])

    properties = {
        "icp_score": str(int(state["score"])),
        "icp_rationale": state["rationale"][:500],
        "icp_next_action": state["next_action"][:200],
    }

    updated = False

    if state.get("hubspot_contact_id"):
        updated = await update_contact_property(
            contact_id=state["hubspot_contact_id"],
            properties=properties,
        )

    if state.get("hubspot_deal_id"):
        await update_deal_property(
            deal_id=state["hubspot_deal_id"],
            properties=properties,
        )

    # Mark as synced
    if updated or state.get("hubspot_deal_id"):
        async with AsyncSessionLocal() as db:
            score_result = await db.execute(
                select(LeadScore).where(
                    LeadScore.lead_id == uuid.UUID(state["lead_id"])
                )
            )
            lead_score = score_result.scalar_one_or_none()
            if lead_score:
                lead_score.hubspot_updated = True
                await db.commit()

    return state


# ── Node 5: Create Follow-up Task ─────────────────────────────────────────────

async def create_task_node(state: LeadState) -> LeadState:
    """
    Creates a follow-up task for the assigned AE in the platform DB.
    For high-score leads (>= threshold), also creates a HubSpot task.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m1_workforce.models_task import Task
    from app.modules.m7_leads.models import IcpProfile
    from sqlalchemy import select

    logger.info("[Lead] Creating follow-up task for %s", state["company_name"])

    score = state["score"]
    threshold = state.get("icp_high_priority_threshold", 70)

    # Determine urgency
    if score >= 80:
        priority = "urgent"
        deadline_days = 1
    elif score >= 60:
        priority = "high"
        deadline_days = 2
    elif score >= 40:
        priority = "medium"
        deadline_days = 7
    else:
        # Low score — don't create task
        logger.info(
            "[Lead] Score %.0f below task threshold — skipping task creation",
            score,
        )
        return state

    # Create task in platform
    async with AsyncSessionLocal() as db:
        # Find owner user for this agency to assign by
        from app.modules.people_and_tenant.users.models import User
        owner_result = await db.execute(
            select(User).where(
                User.agency_id == uuid.UUID(state["agency_id"]),
                User.role == "owner",
            )
        )
        owner = owner_result.scalar_one_or_none()

        deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days)

        task = Task(
            agency_id=uuid.UUID(state["agency_id"]),
            assigned_to=uuid.UUID(state["assigned_to_id"])
            if state.get("assigned_to_id")
            else None,
            assigned_by=owner.id if owner else None,
            title=(
                f"[Lead Follow-up] {state['company_name']} — "
                f"ICP Score {int(score)}/100"
            ),
            description=(
                f"Lead: {state['full_name']} ({state['designation'] or 'N/A'})\n"
                f"Company: {state['company_name']}\n"
                f"Score: {int(score)}/100\n\n"
                f"Rationale: {state['rationale']}\n\n"
                f"Recommended Action: {state['next_action']}"
            ),
            priority=priority,
            deadline=deadline,
            status="created",
        )
        db.add(task)
        await db.commit()

    logger.info(
        "[Lead] Task created for %s (priority=%s, due=%s days)",
        state["company_name"],
        priority,
        deadline_days,
    )

    return state


# ── Node 6: Notify ───────────────────────────────────────────────────────────

async def notify_node(state: LeadState) -> LeadState:
    """
    Sends Slack notification to owner with the lead score summary.
    Stub until Slack SDK wired in frontend phase.
    """
    score = state["score"]

    if score >= 80:
        emoji = "🔥"
        urgency = "HOT LEAD"
    elif score >= 60:
        emoji = "⭐"
        urgency = "Warm Lead"
    elif score >= 40:
        emoji = "🌤"
        urgency = "Lukewarm"
    else:
        emoji = "❄️"
        urgency = "Poor Fit"

    strengths_text = "\n".join(
        f"  ✓ {s}" for s in state["strengths"][:3]
    )
    concerns_text = "\n".join(
        f"  ✗ {c}" for c in state["concerns"][:2]
    )

    message = (
        f"{emoji} *New Lead Scored — {urgency}*\n"
        f"*{state['full_name']}* at *{state['company_name']}*\n"
        f"ICP Score: *{int(score)}/100*\n\n"
        f"*Strengths:*\n{strengths_text}\n\n"
        f"*Concerns:*\n{concerns_text}\n\n"
        f"*Next Action:* {state['next_action']}"
    )

    # TODO: replace with Slack SDK call
    logger.warning("[SLACK STUB] Lead notification:\n%s", message)

    return state


# ── Build graph ──────────────────────────────────────────────────────────────

def build_lead_graph() -> StateGraph:
    graph = StateGraph(LeadState)

    graph.add_node("intake_lead", intake_lead_node)
    graph.add_node("fetch_context", fetch_context_node)
    graph.add_node("score_against_icp", score_against_icp_node)
    graph.add_node("write_back_hubspot", write_back_hubspot_node)
    graph.add_node("create_task", create_task_node)
    graph.add_node("notify", notify_node)

    graph.set_entry_point("intake_lead")
    graph.add_edge("intake_lead", "fetch_context")
    graph.add_edge("fetch_context", "score_against_icp")
    graph.add_edge("score_against_icp", "write_back_hubspot")
    graph.add_edge("write_back_hubspot", "create_task")
    graph.add_edge("create_task", "notify")
    graph.add_edge("notify", END)

    return graph.compile()


# ── Runner ───────────────────────────────────────────────────────────────────

async def run_lead_agent(
    lead_id: str,
    agency_id: str,
) -> dict:
    graph = build_lead_graph()

    initial_state: LeadState = {
        "lead_id": lead_id,
        "agency_id": agency_id,
        "full_name": "",
        "email": "",
        "company_name": "",
        "company_size": None,
        "industry": None,
        "monthly_ad_budget": None,
        "designation": None,
        "pain_points": None,
        "website": None,
        "source": "manual",
        "hubspot_deal_id": None,
        "hubspot_contact_id": None,
        "assigned_to_id": None,
        "icp_ideal_industries": "",
        "icp_company_size": "",
        "icp_ad_budget": "",
        "icp_decision_maker": "",
        "icp_pain_points": "",
        "icp_disqualifiers": "",
        "icp_high_priority_threshold": 70,
        "score": 0.0,
        "rationale": "",
        "strengths": [],
        "concerns": [],
        "next_action": "",
        "errors": [],
    }

    return await graph.ainvoke(initial_state)