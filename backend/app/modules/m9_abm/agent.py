"""
M9 — ABM Orchestration Agent

LangGraph StateGraph — six nodes:
  1. evaluate_state      — reads account journey stage, touch history,
                           engagement signals, days since last touch
  2. recommend_next_touch— Claude decides what the next touch should be
                           (channel, type, timing, message angle)
  3. generate_content    — Claude writes the actual message content
  4. route_channel       — dispatches via Gmail / WATI / LinkedIn stub / ad API
  5. log_touch           — writes AbmTouch record to DB
  6. update_journey      — advances stage if conditions are met,
                           updates ai_next_action on account

Stage advancement rules:
  identified  → researching   : automatic (on first orchestration run)
  researching → first_touch   : after 1+ research touches logged
  first_touch → engaged       : when inbound response received
  engaged     → proposal      : when AE manually advances (or owner triggers)
  proposal    → closed_*      : manually by AE/owner
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

class AbmState(TypedDict):
    # Inputs
    account_id: str
    agency_id: str

    # Account data (populated in node 1)
    company_name: str
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    industry: str | None
    stage: str
    days_since_last_touch: int
    total_touches: int
    last_touch_channel: str | None
    last_touch_outcome: str | None
    intelligence_summary: str | None

    # Touch history summary (last 5 touches)
    touch_history_text: str

    # Competitor context from Qdrant
    competitor_context: str

    # AI decisions
    recommended_channel: str
    recommended_touch_type: str
    recommended_timing: str
    recommendation_rationale: str
    generated_subject: str | None
    generated_content: str

    # Execution
    touch_logged: bool
    stage_advanced: bool
    new_stage: str | None

    errors: list[str]


# ── Node 1: Evaluate State ───────────────────────────────────────────────────

async def evaluate_state_node(state: AbmState) -> AbmState:
    """
    Loads account from DB, computes engagement signals,
    pulls competitor context from Qdrant.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m9_abm.models import AbmAccount, AbmTouch
    from app.core.vector_store import search_similar, RESEARCH_COLLECTION
    from sqlalchemy import select

    logger.info("[ABM] Evaluating state for account %s", state["account_id"])

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AbmAccount).where(
                AbmAccount.id == uuid.UUID(state["account_id"])
            )
        )
        account = result.scalar_one_or_none()

        if not account:
            state["errors"].append("Account not found")
            return state

        state["company_name"] = account.company_name
        state["contact_name"] = account.contact_name
        state["contact_email"] = account.contact_email
        state["contact_phone"] = account.contact_phone
        state["industry"] = account.industry
        state["stage"] = account.stage
        state["intelligence_summary"] = account.intelligence_summary

        # Calculate days since last touch
        now = datetime.now(timezone.utc)
        if account.last_touch_at:
            delta = now - account.last_touch_at
            state["days_since_last_touch"] = delta.days
        else:
            state["days_since_last_touch"] = 999

        # Fetch touch history
        touches_result = await db.execute(
            select(AbmTouch).where(
                AbmTouch.account_id == account.id
            ).order_by(AbmTouch.touched_at.desc()).limit(5)
        )
        touches = touches_result.scalars().all()
        state["total_touches"] = len(touches)

        if touches:
            state["last_touch_channel"] = touches[0].channel
            state["last_touch_outcome"] = touches[0].outcome

            history_lines = []
            for t in touches:
                outcome_str = f" → {t.outcome}" if t.outcome else ""
                history_lines.append(
                    f"Day -{(now - t.touched_at).days}: "
                    f"{t.channel} {t.direction} ({t.touch_type}){outcome_str}"
                )
            state["touch_history_text"] = "\n".join(history_lines)
        else:
            state["last_touch_channel"] = None
            state["last_touch_outcome"] = None
            state["touch_history_text"] = "No touches yet"

    # Pull competitor context from Qdrant
    search_query = (
        f"{state.get('industry', '')} {state['company_name']} "
        f"competitor marketing strategy"
    ).strip()

    try:
        results = await search_similar(
            collection_name=RESEARCH_COLLECTION,
            query_text=search_query,
            top_k=2,
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
                findings = r["payload"].get("key_findings", [])[:2]
                competitor = r["payload"].get("competitor_name", "")
                if findings:
                    context_parts.append(
                        f"{competitor}: " + "; ".join(findings)
                    )
            state["competitor_context"] = (
                "\n".join(context_parts)
                or "No competitor data available"
            )
        else:
            state["competitor_context"] = "No competitor data available"

    except Exception as e:
        logger.warning("[ABM] Qdrant search failed: %s", e)
        state["competitor_context"] = "Competitor data unavailable"

    return state


# ── Node 2: Recommend Next Touch ──────────────────────────────────────────────

async def recommend_next_touch_node(state: AbmState) -> AbmState:
    """
    Claude evaluates the account state and recommends:
    - Which channel to use next
    - What type of touch (follow_up, content_share, proposal, etc.)
    - When to send (immediately, in X days)
    - The strategic rationale
    """
    from app.config import settings

    logger.info("[ABM] Getting touch recommendation for %s", state["company_name"])

    if not settings.anthropic_api_key:
        state["recommended_channel"] = "email"
        state["recommended_touch_type"] = "follow_up"
        state["recommended_timing"] = "immediately"
        state["recommendation_rationale"] = "Default recommendation — API key not configured"
        return state

    stage_context = {
        "identified": "We know about this company but haven't contacted them.",
        "researching": "We're gathering intelligence before first contact.",
        "first_touch": "We've made initial contact. Goal is to get a response.",
        "engaged": "They've responded. Goal is to build relationship and qualify.",
        "proposal": "We're in active discussions. Goal is to close.",
        "closed_won": "This account converted. No further ABM needed.",
        "closed_lost": "This account was lost. No further ABM needed.",
    }

    prompt = f"""You are an ABM (Account-Based Marketing) strategist.

ACCOUNT: {state["company_name"]}
Contact: {state.get("contact_name") or "Unknown"} ({state.get("contact_email") or "no email"})
Industry: {state.get("industry") or "Unknown"}
Current Stage: {state["stage"]}
Stage Context: {stage_context.get(state["stage"], "")}

ENGAGEMENT DATA:
Days since last touch: {state["days_since_last_touch"]}
Total touches made: {state["total_touches"]}
Last touch channel: {state.get("last_touch_channel") or "none"}
Last touch outcome: {state.get("last_touch_outcome") or "unknown"}

TOUCH HISTORY (most recent first):
{state["touch_history_text"]}

COMPETITOR INTELLIGENCE:
{state["competitor_context"]}

Recommend the optimal next touch for this account.

Rules:
- Never repeat the same channel twice in a row
- If last touch got no_response and it was email, try LinkedIn next
- If 14+ days since last touch with no response, send a breakup email
- If engaged stage, focus on value delivery not just follow-up
- If proposal stage, be direct about next steps

Respond ONLY in this exact JSON format:
{{
  "channel": "email|linkedin|whatsapp|call|meeting",
  "touch_type": "first_contact|follow_up|content_share|proposal|breakup|other",
  "timing": "immediately|in_2_days|in_3_days|in_5_days|in_7_days",
  "rationale": "<one sentence explaining this recommendation>",
  "message_angle": "<what angle/hook the message should use>"
}}"""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(response.content[0].text.strip())

        state["recommended_channel"] = result.get("channel", "email")
        state["recommended_touch_type"] = result.get("touch_type", "follow_up")
        state["recommended_timing"] = result.get("timing", "immediately")
        state["recommendation_rationale"] = result.get("rationale", "")

        # Store message angle for content generation
        state["intelligence_summary"] = (
            result.get("message_angle", "")
            + "\n\n"
            + (state.get("competitor_context") or "")
        )

        logger.info(
            "[ABM] Recommendation for %s: %s via %s (%s)",
            state["company_name"],
            state["recommended_touch_type"],
            state["recommended_channel"],
            state["recommended_timing"],
        )

    except Exception as e:
        logger.error("[ABM] Recommendation failed: %s", e)
        state["errors"].append(f"recommend_next_touch: {e}")
        state["recommended_channel"] = "email"
        state["recommended_touch_type"] = "follow_up"
        state["recommended_timing"] = "immediately"
        state["recommendation_rationale"] = "Default — AI unavailable"

    return state


# ── Node 3: Generate Content ──────────────────────────────────────────────────

async def generate_content_node(state: AbmState) -> AbmState:
    """
    Claude writes the actual message content for the recommended touch.
    Uses the message angle from node 2 as creative direction.
    """
    from app.config import settings

    logger.info(
        "[ABM] Generating %s content for %s",
        state["recommended_channel"],
        state["company_name"],
    )

    if not settings.anthropic_api_key:
        state["generated_subject"] = f"Following up — {state['company_name']}"
        state["generated_content"] = (
            f"Hi {state.get('contact_name', 'there')},\n\n"
            f"Just following up on my previous message.\n\nBest regards"
        )
        return state

    channel = state["recommended_channel"]
    touch_type = state["recommended_touch_type"]
    contact_first = (
        state.get("contact_name", "there").split()[0]
        if state.get("contact_name")
        else "there"
    )
    stage = state["stage"]
    angle = state.get("intelligence_summary", "")

    # Build channel-specific instructions
    if channel == "email":
        length_guide = "80-140 words"
        format_guide = "professional email with subject line"
    elif channel == "linkedin":
        length_guide = "50-80 words"
        format_guide = "casual LinkedIn DM, no subject"
    elif channel == "whatsapp":
        length_guide = "30-60 words"
        format_guide = "short WhatsApp message, conversational"
    else:
        length_guide = "60-100 words"
        format_guide = "clear and direct"

    # Breakup email is special
    if touch_type == "breakup":
        breakup_prompt = f"""Write a breakup email for an ABM prospect.

Contact: {contact_first} at {state["company_name"]}
Stage: {stage}

Write a short, dignified breakup message (60-80 words) that:
- Acknowledges they may not be interested
- Leaves the door open for future
- Does NOT beg or apply pressure
- Ends with a genuine "no worries" out

Format: subject line then body. Separate with "---"
Return only the message, no other text."""

        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=300,
                messages=[{"role": "user", "content": breakup_prompt}],
            )
            raw = response.content[0].text.strip()
            if "---" in raw:
                parts = raw.split("---", 1)
                state["generated_subject"] = parts[0].strip()
                state["generated_content"] = parts[1].strip()
            else:
                state["generated_subject"] = "Closing the loop"
                state["generated_content"] = raw
            return state
        except Exception as e:
            logger.error("[ABM] Breakup email generation failed: %s", e)

    # Standard message generation
    prompt = f"""Write a {channel} message for an ABM outreach.

Contact: {contact_first} at {state["company_name"]}
Industry: {state.get("industry") or "unknown"}
Stage: {stage}
Touch type: {touch_type}
Strategic angle: {angle or "build relationship, demonstrate value"}

Competitor intelligence to reference (use subtly, don't name competitors):
{state.get("competitor_context", "None available")}

Requirements:
- Format: {format_guide}
- Length: {length_guide}
- One clear CTA at the end
- Reference specific industry context
- Sound human, not templated
- First name greeting only

{"For email: write subject on first line, then blank line, then body." if channel == "email" else "Write only the message body."}
Return only the message, no other text."""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        if channel == "email" and "\n" in raw:
            lines = raw.split("\n", 1)
            state["generated_subject"] = lines[0].strip()
            state["generated_content"] = lines[1].strip() if len(lines) > 1 else raw
        else:
            state["generated_subject"] = None
            state["generated_content"] = raw

        logger.info(
            "[ABM] Content generated for %s (%d chars)",
            state["company_name"],
            len(state["generated_content"]),
        )

    except Exception as e:
        logger.error("[ABM] Content generation failed: %s", e)
        state["errors"].append(f"generate_content: {e}")
        state["generated_subject"] = f"Checking in — {state['company_name']}"
        state["generated_content"] = (
            f"Hi {contact_first},\n\nJust wanted to touch base. "
            f"Would love to connect when the timing is right.\n\nBest"
        )

    return state


# ── Node 4: Route Channel ─────────────────────────────────────────────────────

async def route_channel_node(state: AbmState) -> AbmState:
    """
    Routes the generated content to the appropriate channel.
    All channels are stubbed — real integrations use the
    same Gmail/WATI utilities already built in M1/M5.
    """
    channel = state["recommended_channel"]
    contact = state.get("contact_name", "the contact")
    company = state["company_name"]

    if channel == "email":
        email = state.get("contact_email")
        if email:
            # TODO: call Gmail API with agency OAuth token
            logger.warning(
                "[GMAIL STUB] ABM email to %s (%s): %s",
                email,
                company,
                state.get("generated_subject", ""),
            )
        else:
            logger.warning(
                "[ABM] No email address for %s — cannot send email",
                company,
            )
            state["errors"].append("No contact email — email not sent")

    elif channel == "linkedin":
        logger.warning(
            "[LINKEDIN STUB] ABM LinkedIn DM to %s at %s: %s",
            contact,
            company,
            state["generated_content"][:80],
        )

    elif channel == "whatsapp":
        phone = state.get("contact_phone")
        if phone:
            # TODO: call WATI API
            logger.warning(
                "[WATI STUB] ABM WhatsApp to %s (%s): %s",
                phone,
                company,
                state["generated_content"][:80],
            )
        else:
            logger.warning(
                "[ABM] No phone for %s — cannot send WhatsApp",
                company,
            )

    elif channel in ("call", "meeting"):
        logger.warning(
            "[ABM] Reminder: Schedule %s with %s at %s",
            channel,
            contact,
            company,
        )

    return state


# ── Node 5: Log Touch ─────────────────────────────────────────────────────────

async def log_touch_node(state: AbmState) -> AbmState:
    """
    Writes the AbmTouch record to DB and updates
    last_touch_at + ai_next_action on the account.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m9_abm.models import AbmAccount, AbmTouch
    from sqlalchemy import select

    logger.info("[ABM] Logging touch for %s", state["company_name"])

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        touch = AbmTouch(
            account_id=uuid.UUID(state["account_id"]),
            agency_id=uuid.UUID(state["agency_id"]),
            channel=state["recommended_channel"],
            direction="outbound",
            touch_type=state["recommended_touch_type"],
            subject=state.get("generated_subject"),
            content=state["generated_content"],
            ai_generated=True,
            touched_at=now,
        )
        db.add(touch)

        # Update account
        acct_result = await db.execute(
            select(AbmAccount).where(
                AbmAccount.id == uuid.UUID(state["account_id"])
            )
        )
        account = acct_result.scalar_one_or_none()
        if account:
            account.last_touch_at = now
            account.ai_next_action = state["recommendation_rationale"]

        await db.commit()

    state["touch_logged"] = True
    return state


# ── Node 6: Update Journey ────────────────────────────────────────────────────

async def update_journey_node(state: AbmState) -> AbmState:
    """
    Evaluates whether the account should advance to the next stage.

    Automatic advancement rules:
      identified  → researching : always (first orchestration run)
      researching → first_touch : when total touches >= 1
      (all other transitions require manual owner action)
    """
    from app.database import AsyncSessionLocal
    from app.modules.m9_abm.models import AbmAccount, ABM_STAGES
    from sqlalchemy import select

    current_stage = state["stage"]
    new_stage = None
    now = datetime.now(timezone.utc)

    # Automatic advancement logic
    if current_stage == "identified":
        new_stage = "researching"
    elif current_stage == "researching" and state["total_touches"] >= 1:
        new_stage = "first_touch"

    if new_stage and new_stage in ABM_STAGES:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AbmAccount).where(
                    AbmAccount.id == uuid.UUID(state["account_id"])
                )
            )
            account = result.scalar_one_or_none()
            if account:
                account.stage = new_stage
                account.stage_entered_at = now
                await db.commit()

        state["stage_advanced"] = True
        state["new_stage"] = new_stage
        logger.info(
            "[ABM] %s advanced: %s → %s",
            state["company_name"],
            current_stage,
            new_stage,
        )
    else:
        state["stage_advanced"] = False
        state["new_stage"] = None

    # Slack notification
    stage_text = (
        f" (advanced to *{new_stage}*)" if new_stage else ""
    )
    logger.warning(
        "[SLACK STUB] ABM touch logged for *%s*%s — "
        "channel: %s, type: %s",
        state["company_name"],
        stage_text,
        state["recommended_channel"],
        state["recommended_touch_type"],
    )

    return state


# ── Build Graph ──────────────────────────────────────────────────────────────

def build_abm_graph() -> StateGraph:
    graph = StateGraph(AbmState)

    graph.add_node("evaluate_state", evaluate_state_node)
    graph.add_node("recommend_next_touch", recommend_next_touch_node)
    graph.add_node("generate_content", generate_content_node)
    graph.add_node("route_channel", route_channel_node)
    graph.add_node("log_touch", log_touch_node)
    graph.add_node("update_journey", update_journey_node)

    graph.set_entry_point("evaluate_state")
    graph.add_edge("evaluate_state", "recommend_next_touch")
    graph.add_edge("recommend_next_touch", "generate_content")
    graph.add_edge("generate_content", "route_channel")
    graph.add_edge("route_channel", "log_touch")
    graph.add_edge("log_touch", "update_journey")
    graph.add_edge("update_journey", END)

    return graph.compile()


# ── Runner ───────────────────────────────────────────────────────────────────

async def run_abm_agent(
    account_id: str,
    agency_id: str,
) -> dict:
    graph = build_abm_graph()

    initial_state: AbmState = {
        "account_id": account_id,
        "agency_id": agency_id,
        "company_name": "",
        "contact_name": None,
        "contact_email": None,
        "contact_phone": None,
        "industry": None,
        "stage": "identified",
        "days_since_last_touch": 999,
        "total_touches": 0,
        "last_touch_channel": None,
        "last_touch_outcome": None,
        "intelligence_summary": None,
        "touch_history_text": "",
        "competitor_context": "",
        "recommended_channel": "email",
        "recommended_touch_type": "first_contact",
        "recommended_timing": "immediately",
        "recommendation_rationale": "",
        "generated_subject": None,
        "generated_content": "",
        "touch_logged": False,
        "stage_advanced": False,
        "new_stage": None,
        "errors": [],
    }

    return await graph.ainvoke(initial_state)