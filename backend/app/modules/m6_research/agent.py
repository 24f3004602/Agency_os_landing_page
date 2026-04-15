"""
M6 — Research Agent

LangGraph StateGraph — five nodes:
  1. fetch_competitor_ads  — Meta Ad Library pull
  2. fetch_serp_data       — SerpAPI Google results pull
  3. synthesise_brief      — Claude generates competitive intelligence brief
  4. store_vectors         — stores brief in Qdrant for M4/M8 retrieval
  5. deliver               — saves to DB, logs to owner feed

Runs per competitor per client.
The Celery job calls this once per tracked competitor per research run.
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

class ResearchState(TypedDict):
    # Inputs
    brief_id: str
    agency_id: str
    client_id: str
    client_name: str
    competitor_id: str
    competitor_name: str
    meta_page_id: str | None
    domain: str | None
    industry: str | None

    # Data collected
    meta_ads_data: dict
    serp_data: dict

    # Claude outputs
    brief_text: str
    key_findings: list[str]

    # Storage
    qdrant_point_id: str | None

    errors: list[str]


# ── Node 1: Fetch Competitor Ads ─────────────────────────────────────────────

async def fetch_competitor_ads_node(state: ResearchState) -> ResearchState:
    """Pulls active ads from Meta Ad Library for the competitor."""
    from app.core.competitor_data import fetch_meta_ads

    logger.info(
        "[Research] Fetching Meta ads for %s",
        state["competitor_name"],
    )

    try:
        data = await fetch_meta_ads(
            page_id=state["meta_page_id"] or "",
        )
        state["meta_ads_data"] = data
    except Exception as e:
        logger.error("[Research] Meta fetch failed: %s", e)
        state["errors"].append(f"fetch_meta_ads: {e}")
        state["meta_ads_data"] = {}

    return state


# ── Node 2: Fetch SERP Data ──────────────────────────────────────────────────

async def fetch_serp_data_node(state: ResearchState) -> ResearchState:
    """Pulls Google search data for the competitor via SerpAPI."""
    from app.core.competitor_data import fetch_serp_data

    logger.info(
        "[Research] Fetching SERP data for %s",
        state["competitor_name"],
    )

    try:
        data = await fetch_serp_data(
            competitor_name=state["competitor_name"],
            domain=state["domain"],
            industry=state["industry"],
        )
        state["serp_data"] = data
    except Exception as e:
        logger.error("[Research] SERP fetch failed: %s", e)
        state["errors"].append(f"fetch_serp_data: {e}")
        state["serp_data"] = {}

    # Persist raw data to DB
    await _update_brief_raw_data(
        state["brief_id"],
        state["meta_ads_data"],
        state["serp_data"],
    )

    return state


async def _update_brief_raw_data(
    brief_id: str,
    meta_data: dict,
    serp_data: dict,
) -> None:
    from app.database import AsyncSessionLocal
    from app.modules.m6_research.models import ResearchBrief
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ResearchBrief).where(
                ResearchBrief.id == uuid.UUID(brief_id)
            )
        )
        brief = result.scalar_one_or_none()
        if brief:
            brief.meta_ads_data_json = json.dumps(meta_data)
            brief.serp_data_json = json.dumps(serp_data)
            await db.commit()


# ── Node 3: Synthesise Brief ─────────────────────────────────────────────────

async def synthesise_brief_node(state: ResearchState) -> ResearchState:
    """
    Claude reads the raw competitor data and writes a structured
    competitive intelligence brief.

    Output:
      - brief_text   : full narrative analysis
      - key_findings : 3-5 bullet points for quick scanning
    """
    from app.config import settings

    logger.info(
        "[Research] Synthesising brief for %s",
        state["competitor_name"],
    )

    if not settings.anthropic_api_key:
        state["brief_text"] = "Anthropic API key not configured."
        state["key_findings"] = ["Set ANTHROPIC_API_KEY to enable AI analysis"]
        return state

    meta = state["meta_ads_data"]
    serp = state["serp_data"]

    # Build context string
    meta_context = f"""
Meta Ads Active: {meta.get("active_ad_count", "unknown")}
Sample Ad Texts:
{chr(10).join("- " + t for t in meta.get("sample_ad_texts", [])[:5])}
Data Source: {"Live" if not meta.get("is_stub") else "Sample (no Meta credentials)"}
"""

    paid_ads_text = "\n".join(
        f"- {a.get('title', '')}: {a.get('description', '')}"
        for a in serp.get("paid_ads", [])
    )
    organic_text = "\n".join(
        f"- {r.get('title', '')}: {r.get('snippet', '')}"
        for r in serp.get("organic_results", [])[:3]
    )

    serp_context = f"""
Google Paid Ads Running:
{paid_ads_text or "None detected"}

Organic Presence:
{organic_text or "No organic data"}

Brand Description: {serp.get("knowledge_graph_description", "N/A")}
Data Source: {"Live" if not serp.get("is_stub") else "Sample (no SerpAPI key)"}
"""

    prompt = f"""You are a competitive intelligence analyst at a digital marketing agency.

Your client is: {state["client_name"]}
You are analysing their competitor: {state["competitor_name"]}
Industry: {state["industry"] or "digital marketing"}

COMPETITOR DATA:

META/INSTAGRAM ADS:
{meta_context}

GOOGLE PRESENCE:
{serp_context}

Write a competitive intelligence brief with these exact sections:

1. COMPETITOR OVERVIEW
2-3 sentences on what this competitor is currently doing in their marketing.

2. ACTIVE ADVERTISING STRATEGY
What platforms are they advertising on? What messaging themes?
What creative formats? Any notable offers or CTAs?

3. KEY CHANGES THIS PERIOD
What appears to be new or changed compared to standard industry behaviour?
Be specific — "increased video ad volume" not "more ads".

4. THREAT ASSESSMENT FOR {state["client_name"].upper()}
How does this competitor's activity directly threaten your client?
What positioning overlap exists?

5. RECOMMENDED COUNTER-STRATEGIES
3 specific actions your client could take in response.
Each should be tactical and implementable within 30 days.

Keep the total brief under 500 words.
Be direct, analytical, and actionable.

After the brief, on a new line write:
KEY_FINDINGS:
- [finding 1]
- [finding 2]
- [finding 3]"""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        full_text = response.content[0].text.strip()

        # Split brief from key findings
        if "KEY_FINDINGS:" in full_text:
            parts = full_text.split("KEY_FINDINGS:")
            brief_text = parts[0].strip()
            findings_raw = parts[1].strip()
            key_findings = [
                line.lstrip("- ").strip()
                for line in findings_raw.split("\n")
                if line.strip() and line.strip() != "-"
            ]
        else:
            brief_text = full_text
            key_findings = [
                f"Competitor {state['competitor_name']} has "
                f"{meta.get('active_ad_count', 'unknown')} active Meta ads"
            ]

        state["brief_text"] = brief_text
        state["key_findings"] = key_findings[:5]  # cap at 5
        logger.info(
            "[Research] Brief generated for %s (%d chars)",
            state["competitor_name"],
            len(brief_text),
        )

    except Exception as e:
        logger.error("[Research] Claude synthesis failed: %s", e)
        state["errors"].append(f"synthesise_brief: {e}")
        state["brief_text"] = f"Brief generation failed: {e}"
        state["key_findings"] = ["AI synthesis unavailable — check API key"]

    return state


# ── Node 4: Store Vectors ─────────────────────────────────────────────────────

async def store_vectors_node(state: ResearchState) -> ResearchState:
    """
    Stores the brief in Qdrant so M4 (churn enrichment)
    and M8 (outreach personalisation) can retrieve it via
    semantic search.

    Payload stored alongside vector:
      - brief_id, competitor_name, client_id, agency_id
      - key_findings (for quick preview without DB query)
    """
    from app.core.vector_store import store_point, RESEARCH_COLLECTION

    logger.info(
        "[Research] Storing vector for %s",
        state["competitor_name"],
    )

    # Text to embed = brief_text + key findings for richer semantic content
    embed_text = (
        f"Competitor: {state['competitor_name']}\n"
        f"Client: {state['client_name']}\n\n"
        f"{state['brief_text']}\n\n"
        f"Key findings: {'; '.join(state['key_findings'])}"
    )

    payload = {
        "brief_id": state["brief_id"],
        "competitor_name": state["competitor_name"],
        "competitor_id": state["competitor_id"],
        "client_id": state["client_id"],
        "client_name": state["client_name"],
        "agency_id": state["agency_id"],
        "key_findings": state["key_findings"],
        "brief_preview": state["brief_text"][:500],
        "industry": state["industry"],
    }

    try:
        point_id = await store_point(
            collection_name=RESEARCH_COLLECTION,
            point_id=state["brief_id"],
            text=embed_text,
            payload=payload,
        )
        state["qdrant_point_id"] = point_id
        logger.info("[Research] Stored in Qdrant: %s", point_id)
    except Exception as e:
        logger.error("[Research] Qdrant storage failed: %s", e)
        state["errors"].append(f"store_vectors: {e}")
        state["qdrant_point_id"] = None

    return state


# ── Node 5: Deliver ──────────────────────────────────────────────────────────

async def deliver_node(state: ResearchState) -> ResearchState:
    """
    Persists the final brief to PostgreSQL
    and logs a stub Slack notification to the owner.
    """
    from app.database import AsyncSessionLocal
    from app.modules.m6_research.models import ResearchBrief
    from sqlalchemy import select

    logger.info(
        "[Research] Delivering brief for %s",
        state["competitor_name"],
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ResearchBrief).where(
                ResearchBrief.id == uuid.UUID(state["brief_id"])
            )
        )
        brief = result.scalar_one_or_none()
        if brief:
            brief.brief_text = state["brief_text"]
            brief.key_findings_json = json.dumps(state["key_findings"])
            brief.qdrant_point_id = state["qdrant_point_id"]
            await db.commit()

    # Stub Slack notification to owner
    findings_text = "\n".join(
        f"  • {f}" for f in state["key_findings"][:3]
    )
    logger.warning(
        "[SLACK STUB] Research brief ready — %s:\n%s",
        state["competitor_name"],
        findings_text,
    )

    return state


# ── Build graph ──────────────────────────────────────────────────────────────

def build_research_graph() -> StateGraph:
    graph = StateGraph(ResearchState)

    graph.add_node("fetch_competitor_ads", fetch_competitor_ads_node)
    graph.add_node("fetch_serp_data", fetch_serp_data_node)
    graph.add_node("synthesise_brief", synthesise_brief_node)
    graph.add_node("store_vectors", store_vectors_node)
    graph.add_node("deliver", deliver_node)

    graph.set_entry_point("fetch_competitor_ads")
    graph.add_edge("fetch_competitor_ads", "fetch_serp_data")
    graph.add_edge("fetch_serp_data", "synthesise_brief")
    graph.add_edge("synthesise_brief", "store_vectors")
    graph.add_edge("store_vectors", "deliver")
    graph.add_edge("deliver", END)

    return graph.compile()


# ── Runner ───────────────────────────────────────────────────────────────────

async def run_research_agent(
    brief_id: str,
    agency_id: str,
    client_id: str,
    client_name: str,
    competitor_id: str,
    competitor_name: str,
    meta_page_id: str | None = None,
    domain: str | None = None,
    industry: str | None = None,
) -> dict:
    graph = build_research_graph()

    initial_state: ResearchState = {
        "brief_id": brief_id,
        "agency_id": agency_id,
        "client_id": client_id,
        "client_name": client_name,
        "competitor_id": competitor_id,
        "competitor_name": competitor_name,
        "meta_page_id": meta_page_id,
        "domain": domain,
        "industry": industry,
        "meta_ads_data": {},
        "serp_data": {},
        "brief_text": "",
        "key_findings": [],
        "qdrant_point_id": None,
        "errors": [],
    }

    return await graph.ainvoke(initial_state)