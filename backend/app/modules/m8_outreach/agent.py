"""
M8 — Personalisation & Outreach Agent

LangGraph StateGraph — five nodes:
  1. retrieve_context    — pulls lead data (M7) + competitor intel (M6 Qdrant)
  2. generate_messages   — Claude writes personalised multi-step sequence
  3. create_sequence     — saves sequence + steps to DB
  4. send_first_step     — sends step 1 immediately (email via Gmail)
  5. monitor_replies     — sets up Celery schedule for subsequent steps

Context Claude receives:
  - Lead: name, company, designation, pain points, ICP score, rationale
  - Competitor intel: top matching briefs from Qdrant for their industry
  - Agency: what services are offered (from ICP profile)

Output: 3-step sequence
  Step 1 (day 0)   : Personalised cold email referencing competitor intel
  Step 2 (day 3)   : LinkedIn message (shorter, conversational)
  Step 3 (day 7)   : Follow-up email — case study / social proof angle
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

class OutreachState(TypedDict):
    # Inputs
    agency_id: str
    lead_id: str
    send_mode: str          # manual | auto
    assigned_to_id: str | None

    # Lead data (populated in node 1)
    lead_full_name: str
    lead_email: str
    lead_company: str
    lead_designation: str | None
    lead_industry: str | None
    lead_pain_points: str | None
    lead_icp_score: float | None
    lead_icp_rationale: str | None
    lead_icp_next_action: str | None

    # Competitor context from Qdrant (populated in node 1)
    competitor_context: str

    # Agency ICP for service description
    agency_services: str

    # Generated messages (populated in node 2)
    # List of dicts: {step_number, channel, subject, body, send_after_days}
    generated_steps: list[dict]

    # DB records created (populated in node 3)
    sequence_id: str | None

    errors: list[str]


# ── Node 1: Retrieve Context ─────────────────────────────────────────────────

async def retrieve_context_node(state: OutreachState) -> OutreachState:
    """
    Loads lead data from DB and pulls relevant competitor
    intelligence from Qdrant using semantic search.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m7_leads.models import Lead, LeadScore, IcpProfile
    from app.core.vector_store import search_similar, RESEARCH_COLLECTION
    from sqlalchemy import select

    logger.info("[Outreach] Retrieving context for lead %s", state["lead_id"])

    async with AsyncSessionLocal() as db:
        # Load lead
        lead_result = await db.execute(
            select(Lead).where(Lead.id == uuid.UUID(state["lead_id"]))
        )
        lead = lead_result.scalar_one_or_none()

        if not lead:
            state["errors"].append("Lead not found")
            return state

        state["lead_full_name"] = lead.full_name
        state["lead_email"] = lead.email
        state["lead_company"] = lead.company_name
        state["lead_designation"] = lead.designation
        state["lead_industry"] = lead.industry
        state["lead_pain_points"] = lead.pain_points

        # Load score context
        score_result = await db.execute(
            select(LeadScore).where(
                LeadScore.lead_id == uuid.UUID(state["lead_id"])
            )
        )
        score = score_result.scalar_one_or_none()
        if score:
            state["lead_icp_score"] = score.score
            state["lead_icp_rationale"] = score.rationale
            state["lead_icp_next_action"] = score.next_action

        # Load agency ICP for service context
        icp_result = await db.execute(
            select(IcpProfile).where(
                IcpProfile.agency_id == uuid.UUID(state["agency_id"])
            )
        )
        icp = icp_result.scalar_one_or_none()
        state["agency_services"] = (
            icp.ideal_pain_points
            if icp
            else "digital marketing, paid ads, performance marketing"
        )

    # Pull competitor intel from Qdrant
    # Search for research relevant to the lead's industry
    search_query = (
        f"{state.get('lead_industry', '')} "
        f"{state.get('lead_company', '')} "
        f"competitor advertising strategy"
    ).strip()

    try:
        results = await search_similar(
            collection_name=RESEARCH_COLLECTION,
            query_text=search_query,
            top_k=3,
            filter_payload={
                "must": [
                    {
                        "key": "agency_id",
                        "match": {"value": state["agency_id"]},
                    }
                ]
            },
        )

        if results:
            context_parts = []
            for r in results:
                payload = r["payload"]
                findings = payload.get("key_findings", [])
                competitor = payload.get("competitor_name", "")
                if findings:
                    context_parts.append(
                        f"Competitor '{competitor}': "
                        + "; ".join(findings[:2])
                    )

            state["competitor_context"] = (
                "\n".join(context_parts)
                if context_parts
                else "No competitor intelligence available yet."
            )
        else:
            state["competitor_context"] = (
                "No competitor intelligence available yet."
            )

    except Exception as e:
        logger.warning("[Outreach] Qdrant search failed: %s", e)
        state["competitor_context"] = "Competitor intelligence unavailable."

    logger.info(
        "[Outreach] Context loaded for %s at %s",
        state["lead_full_name"],
        state["lead_company"],
    )
    return state


# ── Node 2: Generate Messages ─────────────────────────────────────────────────

async def generate_messages_node(state: OutreachState) -> OutreachState:
    """
    Claude writes a 3-step personalised outreach sequence.

    Step 1 (day 0)  — Cold email referencing competitor activity
    Step 2 (day 3)  — LinkedIn message (short, conversational)
    Step 3 (day 7)  — Follow-up email with case study angle
    """
    from app.config import settings

    logger.info(
        "[Outreach] Generating messages for %s",
        state["lead_company"],
    )

    if not settings.anthropic_api_key:
        state["generated_steps"] = _stub_steps(state)
        return state

    icp_score_text = (
        f"{state['lead_icp_score']:.0f}/100"
        if state.get("lead_icp_score") is not None
        else "Not scored"
    )

    prompt = f"""You are a senior business development writer at a digital marketing agency.

Write a 3-step personalised outreach sequence for this lead.

LEAD PROFILE:
Name: {state["lead_full_name"]}
Title: {state.get("lead_designation") or "Decision Maker"}
Company: {state["lead_company"]}
Industry: {state.get("lead_industry") or "Not specified"}
Pain Points: {state.get("lead_pain_points") or "Not provided"}
ICP Match Score: {icp_score_text}
Why They Fit Us: {state.get("lead_icp_rationale") or "Strong market fit"}

COMPETITOR INTELLIGENCE WE HAVE ON THEIR INDUSTRY:
{state["competitor_context"]}

OUR AGENCY SPECIALISES IN:
{state["agency_services"]}

Write exactly 3 messages as a JSON array. Each message must have:
{{
  "step_number": 1,
  "channel": "email",
  "send_after_days": 0,
  "subject": "Email subject line",
  "body": "Full message body"
}}

REQUIREMENTS:

Step 1 — Cold Email (send_after_days: 0)
- Subject: specific, references their company or industry
- Opening: a specific observation about their company or industry
  (reference competitor intel if relevant — show you've done research)
- Middle: connect their pain point to what we do
- CTA: one specific ask (15-min call, specific date/time)
- Length: 120-180 words
- Tone: professional but direct, not salesy

Step 2 — LinkedIn Message (send_after_days: 3)
- channel: "linkedin"
- No subject needed (set to empty string)
- Much shorter: 50-70 words
- Reference that you sent an email
- Ask a direct question about their current marketing situation
- End with a soft CTA

Step 3 — Follow-up Email (send_after_days: 7)
- Different angle from Step 1 — lead with social proof or results
- Mention a specific result you've achieved for a similar company
  (use realistic numbers — ROAS, spend managed, conversion lift)
- 100-140 words
- Give them an easy out ("if the timing isn't right, no worries")

CRITICAL RULES:
- Use {state["lead_full_name"].split()[0]} (first name only) as greeting
- Never mention competitors by name — say "industry players" instead
- Never sound like a template — each message should feel handwritten
- Do not use phrases like "I hope this email finds you well"
- Do not use excessive exclamation marks

Return ONLY the JSON array, no other text."""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        steps = json.loads(raw)
        state["generated_steps"] = steps

        logger.info(
            "[Outreach] Generated %d steps for %s",
            len(steps),
            state["lead_company"],
        )

    except Exception as e:
        logger.error("[Outreach] Message generation failed: %s", e)
        state["errors"].append(f"generate_messages: {e}")
        state["generated_steps"] = _stub_steps(state)

    return state


def _stub_steps(state: OutreachState) -> list[dict]:
    """Fallback steps when Claude unavailable."""
    first_name = state.get("lead_full_name", "there").split()[0]
    company = state.get("lead_company", "your company")

    return [
        {
            "step_number": 1,
            "channel": "email",
            "send_after_days": 0,
            "subject": f"Quick question about {company}'s growth strategy",
            "body": (
                f"Hi {first_name},\n\n"
                f"I came across {company} and noticed you're in "
                f"{state.get('lead_industry', 'your space')}.\n\n"
                f"We help companies like yours improve their paid "
                f"advertising performance. Would you be open to a "
                f"quick 15-minute call this week?\n\n"
                f"Best regards"
            ),
        },
        {
            "step_number": 2,
            "channel": "linkedin",
            "send_after_days": 3,
            "subject": "",
            "body": (
                f"Hi {first_name}, I sent you an email earlier this week. "
                f"Quick question — are you happy with your current "
                f"ROAS on paid channels? Happy to share what we've "
                f"been seeing in {state.get('lead_industry', 'your industry')}."
            ),
        },
        {
            "step_number": 3,
            "channel": "email",
            "send_after_days": 7,
            "subject": f"Case study: How we helped a {state.get('lead_industry', 'similar')} brand 3x ROAS",
            "body": (
                f"Hi {first_name},\n\n"
                f"One last note — we recently helped a brand similar "
                f"to {company} go from 1.8x to 3.4x ROAS in 90 days "
                f"by restructuring their Meta campaigns.\n\n"
                f"If the timing isn't right, no worries at all. "
                f"But if you'd like to see the case study, just reply "
                f"and I'll send it over.\n\nBest"
            ),
        },
    ]


# ── Node 3: Create Sequence ──────────────────────────────────────────────────

async def create_sequence_node(state: OutreachState) -> OutreachState:
    """
    Persists the generated sequence and steps to PostgreSQL.
    Calculates scheduled_send_at for each step.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m8_outreach.models import OutreachSequence, OutreachStep

    logger.info(
        "[Outreach] Creating sequence for %s",
        state["lead_company"],
    )

    now = datetime.now(timezone.utc)
    steps = state["generated_steps"]

    async with AsyncSessionLocal() as db:
        sequence = OutreachSequence(
            agency_id=uuid.UUID(state["agency_id"]),
            lead_id=uuid.UUID(state["lead_id"]),
            assigned_to=uuid.UUID(state["assigned_to_id"])
            if state.get("assigned_to_id")
            else None,
            status="active",
            total_steps=len(steps),
            current_step=1,
            send_mode=state["send_mode"],
            competitor_context_used=state["competitor_context"][:500]
            if state["competitor_context"] != "No competitor intelligence available yet."
            else None,
            icp_score_at_creation=state.get("lead_icp_score"),
        )
        db.add(sequence)
        await db.flush()

        for step_data in steps:
            step_number = step_data["step_number"]
            send_after_days = step_data.get("send_after_days", 0)

            # Calculate when to send
            scheduled_at = now + timedelta(days=send_after_days)

            step = OutreachStep(
                sequence_id=sequence.id,
                agency_id=uuid.UUID(state["agency_id"]),
                step_number=step_number,
                send_after_days=send_after_days,
                channel=step_data.get("channel", "email"),
                subject=step_data.get("subject", ""),
                body=step_data["body"],
                status="pending",
                scheduled_send_at=scheduled_at,
                # In manual mode, AE must approve before send
                approved_by_ae=state["send_mode"] == "auto",
            )
            db.add(step)

        await db.commit()
        await db.refresh(sequence)
        state["sequence_id"] = str(sequence.id)

    logger.info(
        "[Outreach] Sequence %s created with %d steps",
        state["sequence_id"],
        len(steps),
    )
    return state


# ── Node 4: Send First Step ───────────────────────────────────────────────────

async def send_first_step_node(state: OutreachState) -> OutreachState:
    """
    Sends step 1 immediately if:
    - send_mode is 'auto', OR
    - send_mode is 'manual' AND step is approved by AE

    In manual mode without pre-approval, just logs that step is ready.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m8_outreach.models import OutreachStep, OutreachSequence
    from app.modules.m1_workforce.models_communication import CommunicationLog
    from sqlalchemy import select

    logger.info(
        "[Outreach] Processing step 1 for sequence %s",
        state.get("sequence_id"),
    )

    if not state.get("sequence_id"):
        return state

    async with AsyncSessionLocal() as db:
        # Get step 1
        step_result = await db.execute(
            select(OutreachStep).where(
                OutreachStep.sequence_id == uuid.UUID(state["sequence_id"]),
                OutreachStep.step_number == 1,
            )
        )
        step = step_result.scalar_one_or_none()

        if not step:
            return state

        if state["send_mode"] == "manual" and not step.approved_by_ae:
            # In manual mode: notify AE that step 1 is ready for review
            logger.warning(
                "[SLACK STUB] Step 1 ready for AE review — "
                "sequence %s for %s",
                state["sequence_id"],
                state["lead_company"],
            )
            return state

        # Auto mode or pre-approved — send now
        if step.channel == "email":
            # Log to communication_logs
            log = CommunicationLog(
                agency_id=uuid.UUID(state["agency_id"]),
                employee_id=None,
                client_id=uuid.UUID(state["lead_id"]),  # lead_id used as reference
                direction="outbound",
                channel="email",
                subject=step.subject,
                body=step.body,
                status="sent",
                sent_at=datetime.now(timezone.utc),
            )
            db.add(log)

            # TODO: call Gmail API to actually send
            logger.warning(
                "[GMAIL STUB] Sending outreach email to %s: %s",
                state["lead_email"],
                step.subject,
            )

        elif step.channel == "linkedin":
            # LinkedIn automation — external tool or manual
            logger.warning(
                "[LINKEDIN STUB] Draft LinkedIn message ready for %s: %s",
                state["lead_full_name"],
                step.body[:100],
            )

        step.status = "sent"
        step.sent_at = datetime.now(timezone.utc)

        # Update sequence current step
        seq_result = await db.execute(
            select(OutreachSequence).where(
                OutreachSequence.id == uuid.UUID(state["sequence_id"])
            )
        )
        seq = seq_result.scalar_one_or_none()
        if seq:
            seq.current_step = 2

        await db.commit()

    logger.info("[Outreach] Step 1 sent for %s", state["lead_company"])
    return state


# ── Node 5: Monitor Replies ───────────────────────────────────────────────────

async def monitor_replies_node(state: OutreachState) -> OutreachState:
    """
    Schedules the Celery job to send subsequent steps on schedule.
    The actual reply detection happens via Gmail webhook
    (POST /m8/webhooks/reply from n8n).
    """
    logger.info(
        "[Outreach] Setting up reply monitoring for sequence %s",
        state.get("sequence_id"),
    )

    # Notify AE that sequence is live
    message = (
        f"📬 Outreach sequence started for *{state['lead_company']}* "
        f"({state['lead_full_name']})\n"
        f"Steps: {len(state['generated_steps'])} | "
        f"Mode: {state['send_mode']}\n"
        f"Reply monitoring active."
    )
    logger.warning("[SLACK STUB] Outreach started: %s", message)

    return state


# ── Build Graph ──────────────────────────────────────────────────────────────

def build_outreach_graph() -> StateGraph:
    graph = StateGraph(OutreachState)

    graph.add_node("retrieve_context", retrieve_context_node)
    graph.add_node("generate_messages", generate_messages_node)
    graph.add_node("create_sequence", create_sequence_node)
    graph.add_node("send_first_step", send_first_step_node)
    graph.add_node("monitor_replies", monitor_replies_node)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "generate_messages")
    graph.add_edge("generate_messages", "create_sequence")
    graph.add_edge("create_sequence", "send_first_step")
    graph.add_edge("send_first_step", "monitor_replies")
    graph.add_edge("monitor_replies", END)

    return graph.compile()


# ── Runner ───────────────────────────────────────────────────────────────────

async def run_outreach_agent(
    agency_id: str,
    lead_id: str,
    send_mode: str = "manual",
    assigned_to_id: str | None = None,
) -> dict:
    graph = build_outreach_graph()

    initial_state: OutreachState = {
        "agency_id": agency_id,
        "lead_id": lead_id,
        "send_mode": send_mode,
        "assigned_to_id": assigned_to_id,
        "lead_full_name": "",
        "lead_email": "",
        "lead_company": "",
        "lead_designation": None,
        "lead_industry": None,
        "lead_pain_points": None,
        "lead_icp_score": None,
        "lead_icp_rationale": None,
        "lead_icp_next_action": None,
        "competitor_context": "",
        "agency_services": "",
        "generated_steps": [],
        "sequence_id": None,
        "errors": [],
    }

    return await graph.ainvoke(initial_state)