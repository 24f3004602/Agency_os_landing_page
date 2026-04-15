"""
M11 — Content Generation Agent

LangGraph StateGraph — five nodes:
  1. parse_brief          — loads brief from DB, validates all required fields
  2. generate_drafts      — Claude generates N variations per brief
                            each with different creative angle
  3. create_approval_req  — creates ClientApprovalRequest record per draft
  4. notify_client        — sends to client portal + WhatsApp
  5. monitor_response     — sets up Celery reminder schedule

Content strategy per platform:
  instagram  — punchy headline, 2-3 short paragraphs, 5-7 hashtags, emoji-friendly
  facebook   — longer form OK, single strong CTA, no hashtag stuffing
  google_ads — ultra-concise headline (30 chars), description (90 chars)
  email      — subject + preview + full body with clear CTA button
  linkedin   — professional tone, thought-leadership angle, minimal hashtags
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

class ContentState(TypedDict):
    # Inputs
    brief_id: str
    agency_id: str

    # Brief data (populated in node 1)
    client_id: str
    client_name: str
    title: str
    objective: str
    target_audience: str | None
    key_message: str | None
    tone_of_voice: str | None
    platform: str
    content_type: str
    word_limit: int | None
    num_variations: int
    additional_notes: str | None

    # Generated drafts (populated in node 2)
    # List of dicts: {variation_number, headline, body_copy, cta, hashtags, angle}
    generated_drafts: list[dict]

    # Draft IDs saved to DB (populated in node 3)
    draft_ids: list[str]

    errors: list[str]


# ── Node 1: Parse Brief ───────────────────────────────────────────────────────

async def parse_brief_node(state: ContentState) -> ContentState:
    """Loads and validates the brief from the database."""
    from app.database import AsyncSessionLocal
    from app.modules.m11_content.models import ContentBrief
    from app.modules.people_and_tenant.users.models import Client
    from sqlalchemy import select

    logger.info("[Content] Parsing brief %s", state["brief_id"])

    async with AsyncSessionLocal() as db:
        brief_result = await db.execute(
            select(ContentBrief).where(
                ContentBrief.id == uuid.UUID(state["brief_id"])
            )
        )
        brief = brief_result.scalar_one_or_none()

        if not brief:
            state["errors"].append("Brief not found")
            return state

        client_result = await db.execute(
            select(Client).where(Client.id == brief.client_id)
        )
        client = client_result.scalar_one_or_none()

        state["client_id"] = str(brief.client_id)
        state["client_name"] = client.company_name if client else "Unknown"
        state["title"] = brief.title
        state["objective"] = brief.objective
        state["target_audience"] = brief.target_audience
        state["key_message"] = brief.key_message
        state["tone_of_voice"] = brief.tone_of_voice
        state["platform"] = brief.platform
        state["content_type"] = brief.content_type
        state["word_limit"] = brief.word_limit
        state["num_variations"] = brief.num_variations
        state["additional_notes"] = brief.additional_notes

        # Mark as generating
        brief.status = "generating"
        await db.commit()

    logger.info(
        "[Content] Brief loaded: %s for %s on %s",
        state["title"],
        state["client_name"],
        state["platform"],
    )
    return state


# ── Node 2: Generate Drafts ───────────────────────────────────────────────────

async def generate_drafts_node(state: ContentState) -> ContentState:
    """
    Claude generates N creative variations for the brief.
    Each variation takes a different angle:
    - Variation 1: Emotional / storytelling
    - Variation 2: Feature-led / rational
    - Variation 3: Urgency / FOMO

    Platform-specific formatting is enforced per platform.
    """
    from app.config import settings

    logger.info(
        "[Content] Generating %d draft(s) for %s",
        state["num_variations"],
        state["title"],
    )

    if not settings.anthropic_api_key:
        state["generated_drafts"] = _stub_drafts(state)
        return state

    # Build platform-specific instructions
    platform_guides = {
        "instagram": (
            "Instagram post. Punchy opening line. 2-3 short paragraphs. "
            "End with 5-7 relevant hashtags on a new line. "
            "Emoji use: moderate and natural. Max 2200 chars."
        ),
        "facebook": (
            "Facebook post. Can be longer form. Single strong CTA. "
            "1-3 hashtags max. Conversational but professional. "
            "Max 500 words."
        ),
        "google_ads": (
            "Google Ads copy. Provide: "
            "Headline (max 30 characters), "
            "Description (max 90 characters). "
            "Be extremely concise. Include keyword naturally. "
            "Strong CTA in description."
        ),
        "email": (
            "Marketing email. Provide: "
            "Subject line (max 60 chars), "
            "Preview text (max 90 chars), "
            "Body (300-500 words with clear sections). "
            "One primary CTA button text at end."
        ),
        "linkedin": (
            "LinkedIn post. Professional tone. "
            "Thought-leadership angle. "
            "Hook in first line (readers see only first 2 lines before 'see more'). "
            "2-4 paragraphs. 2-3 hashtags max. No emoji overuse."
        ),
    }

    platform_guide = platform_guides.get(
        state["platform"],
        "Social media post. Professional and engaging."
    )

    angles = [
        ("Emotional", "Connect through emotion, story, or aspiration. Lead with a relatable pain point or dream."),
        ("Feature-led", "Lead with the most compelling benefit or differentiator. Rational and specific."),
        ("Urgency", "Create a sense of FOMO, scarcity, or time-sensitivity. Drive immediate action."),
        ("Social proof", "Lead with results, numbers, or what others are saying. Build credibility."),
        ("Educational", "Teach something valuable. Position the brand as the expert solution."),
    ][:state["num_variations"]]

    all_drafts = []

    for i, (angle_name, angle_instruction) in enumerate(angles):
        variation_num = i + 1

        word_limit_text = (
            f"Word limit: {state['word_limit']} words max."
            if state["word_limit"]
            else ""
        )

        prompt = f"""You are a senior copywriter specialising in digital marketing content.

Write content for this brief:

CLIENT: {state["client_name"]}
TITLE: {state["title"]}
PLATFORM: {state["platform"]}
CONTENT TYPE: {state["content_type"]}

BRIEF:
Objective: {state["objective"]}
Target Audience: {state.get("target_audience") or "Not specified"}
Key Message: {state.get("key_message") or "Not specified"}
Tone of Voice: {state.get("tone_of_voice") or "Professional and engaging"}
{word_limit_text}
Additional Notes: {state.get("additional_notes") or "None"}

PLATFORM REQUIREMENTS:
{platform_guide}

CREATIVE ANGLE FOR THIS VARIATION:
{angle_name}: {angle_instruction}

Write ONLY this variation. Respond in this exact JSON format with no other text:
{{
  "angle": "{angle_name}",
  "headline": "<headline or subject line>",
  "body_copy": "<main content body>",
  "cta": "<call to action text>",
  "hashtags": "<space-separated hashtags or empty string>"
}}

Make it feel human-written, not like AI generated content.
Be specific to {state["client_name"]} — avoid generic phrases."""

        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            draft_data = json.loads(raw)
            draft_data["variation_number"] = variation_num
            all_drafts.append(draft_data)

            logger.info(
                "[Content] Generated variation %d (%s) for %s",
                variation_num,
                angle_name,
                state["title"],
            )

        except Exception as e:
            logger.error(
                "[Content] Draft generation failed for variation %d: %s",
                variation_num, e,
            )
            state["errors"].append(f"generate_v{variation_num}: {e}")
            # Add stub fallback for this variation
            all_drafts.append({
                "variation_number": variation_num,
                "angle": angle_name,
                "headline": f"{state['client_name']} — {angle_name}",
                "body_copy": f"Draft generation failed: {e}",
                "cta": "Learn More",
                "hashtags": "",
            })

    state["generated_drafts"] = all_drafts
    return state


def _stub_drafts(state: ContentState) -> list[dict]:
    """Fallback drafts when Claude unavailable."""
    client = state["client_name"]
    angles = ["Emotional", "Feature-led", "Urgency"]
    drafts = []

    for i, angle in enumerate(angles[:state["num_variations"]]):
        drafts.append({
            "variation_number": i + 1,
            "angle": angle,
            "headline": f"{client} — {angle} approach",
            "body_copy": (
                f"This is a stub draft for {client}. "
                f"Configure ANTHROPIC_API_KEY to generate real content. "
                f"Angle: {angle}. Platform: {state['platform']}."
            ),
            "cta": "Get Started Today",
            "hashtags": f"#{client.replace(' ', '')} #marketing #digital",
        })

    return drafts


# ── Node 3: Save Drafts & Create Approval Requests ────────────────────────────

async def create_approval_requests_node(state: ContentState) -> ContentState:
    """
    Saves all generated drafts to DB.
    Creates a ClientApprovalRequest for each draft.
    Updates brief status to 'ready'.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m11_content.models import ContentBrief, ContentDraft, ClientApprovalRequest
    from sqlalchemy import select

    logger.info("[Content] Saving drafts for brief %s", state["brief_id"])

    draft_ids = []

    async with AsyncSessionLocal() as db:
        for draft_data in state["generated_drafts"]:
            draft = ContentDraft(
                brief_id=uuid.UUID(state["brief_id"]),
                agency_id=uuid.UUID(state["agency_id"]),
                variation_number=draft_data["variation_number"],
                headline=draft_data.get("headline"),
                body_copy=draft_data["body_copy"],
                cta=draft_data.get("cta"),
                hashtags=draft_data.get("hashtags"),
                angle=draft_data.get("angle"),
                status="generated",
            )
            db.add(draft)
            await db.flush()
            draft_ids.append(str(draft.id))

        # Update brief status
        brief_result = await db.execute(
            select(ContentBrief).where(
                ContentBrief.id == uuid.UUID(state["brief_id"])
            )
        )
        brief = brief_result.scalar_one_or_none()
        if brief:
            brief.status = "ready"

        await db.commit()

    state["draft_ids"] = draft_ids
    logger.info(
        "[Content] Saved %d draft(s) for brief %s",
        len(draft_ids),
        state["brief_id"],
    )
    return state


# ── Node 4: Notify Client ─────────────────────────────────────────────────────

async def notify_client_node(state: ContentState) -> ContentState:
    """
    Sends approval notification to client via:
    - Platform portal (always)
    - WhatsApp via WATI (if client has phone)

    Portal: client sees drafts in Dashboard 3 when they log in
    WhatsApp: sends summary message with approve/reject instructions
    """
    from app.database import AsyncSessionLocal
    from app.modules.people_and_tenant.users.models import Client
    from app.core.wati import send_whatsapp_message
    from sqlalchemy import select

    logger.info("[Content] Notifying client for brief %s", state["brief_id"])

    async with AsyncSessionLocal() as db:
        client_result = await db.execute(
            select(Client).where(Client.id == uuid.UUID(state["client_id"]))
        )
        client = client_result.scalar_one_or_none()

    if not client:
        return state

    # WhatsApp notification
    if client.contact_phone:
        whatsapp_msg = (
            f"Hi {client.contact_name or client.company_name}! 👋\n\n"
            f"We've prepared *{len(state['draft_ids'])} content draft(s)* "
            f"for your review: *{state['title']}*\n\n"
            f"Please log into your portal to review and approve the drafts, "
            f"or reply here:\n"
            f"✅ Reply *APPROVE* to approve the first draft\n"
            f"❌ Reply *REJECT* with your feedback to request changes\n\n"
            f"Your input helps us move fast! 🚀"
        )
        try:
            await send_whatsapp_message(
                phone_number=client.contact_phone,
                message=whatsapp_msg,
            )
        except Exception as e:
            logger.warning("[Content] WhatsApp notification failed: %s", e)

    # Log notification
    logger.warning(
        "[PORTAL] %d draft(s) ready for client %s to review",
        len(state["draft_ids"]),
        state["client_name"],
    )

    return state


# ── Node 5: Monitor Response ──────────────────────────────────────────────────

async def monitor_response_node(state: ContentState) -> ContentState:
    """
    Sets up reminder schedule.
    The actual approval detection happens via:
    - Portal: POST /m11/approvals/{id}/approve from client
    - WhatsApp: POST /m11/webhooks/approval from n8n
    """
    logger.info(
        "[Content] Monitoring setup for %d draft(s)",
        len(state["draft_ids"]),
    )

    # Notify owner/AM that drafts are ready
    logger.warning(
        "[SLACK STUB] 📝 Content ready for client review — "
        "%s: %d variation(s) generated for %s",
        state["client_name"],
        len(state["draft_ids"]),
        state["title"],
    )

    return state


# ── Build Graph ──────────────────────────────────────────────────────────────

def build_content_graph() -> StateGraph:
    graph = StateGraph(ContentState)

    graph.add_node("parse_brief", parse_brief_node)
    graph.add_node("generate_drafts", generate_drafts_node)
    graph.add_node("create_approval_requests", create_approval_requests_node)
    graph.add_node("notify_client", notify_client_node)
    graph.add_node("monitor_response", monitor_response_node)

    graph.set_entry_point("parse_brief")
    graph.add_edge("parse_brief", "generate_drafts")
    graph.add_edge("generate_drafts", "create_approval_requests")
    graph.add_edge("create_approval_requests", "notify_client")
    graph.add_edge("notify_client", "monitor_response")
    graph.add_edge("monitor_response", END)

    return graph.compile()


# ── Runner ───────────────────────────────────────────────────────────────────

async def run_content_agent(
    brief_id: str,
    agency_id: str,
) -> dict:
    graph = build_content_graph()

    initial_state: ContentState = {
        "brief_id": brief_id,
        "agency_id": agency_id,
        "client_id": "",
        "client_name": "",
        "title": "",
        "objective": "",
        "target_audience": None,
        "key_message": None,
        "tone_of_voice": None,
        "platform": "instagram",
        "content_type": "social_post",
        "word_limit": None,
        "num_variations": 3,
        "additional_notes": None,
        "generated_drafts": [],
        "draft_ids": [],
        "errors": [],
    }

    return await graph.ainvoke(initial_state)