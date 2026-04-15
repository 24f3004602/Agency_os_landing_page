import json
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_module, require_owner
from app.database import get_db
from app.modules.m6_research.models import ResearchBrief, TrackedCompetitor
from app.modules.people_and_tenant.users.models import Client, User
from app.modules.m6_research.schemas import (
    ResearchBriefResponse,
    ResearchBriefSummary,
    ResearchRunRequest,
    TrackedCompetitorCreate,
    TrackedCompetitorResponse,
)

router = APIRouter(prefix="/m6", tags=["M6 - Research Agent"])

M6 = Depends(require_module("M6"))


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


async def _build_competitor_response(
    comp: TrackedCompetitor,
    db: AsyncSession,
) -> TrackedCompetitorResponse:
    client_result = await db.execute(
        select(Client).where(Client.id == comp.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"

    brief_count_result = await db.execute(
        select(ResearchBrief).where(
            ResearchBrief.competitor_id == comp.id
        )
    )
    brief_count = len(brief_count_result.scalars().all())

    return TrackedCompetitorResponse(
        id=comp.id,
        agency_id=comp.agency_id,
        client_id=comp.client_id,
        client_name=client_name,
        competitor_name=comp.competitor_name,
        domain=comp.domain,
        meta_page_id=comp.meta_page_id,
        industry=comp.industry,
        is_active=comp.is_active,
        brief_count=brief_count,
        created_at=comp.created_at,
    )


async def _build_brief_response(
    brief: ResearchBrief,
    db: AsyncSession,
) -> ResearchBriefResponse:
    client_result = await db.execute(
        select(Client).where(Client.id == brief.client_id)
    )
    client = client_result.scalar_one_or_none()
    client_name = client.company_name if client else "Unknown"

    try:
        key_findings = json.loads(brief.key_findings_json)
    except Exception:
        key_findings = []

    meta_ad_count = None
    if brief.meta_ads_data_json:
        try:
            meta_data = json.loads(brief.meta_ads_data_json)
            meta_ad_count = meta_data.get("active_ad_count")
        except Exception:
            pass

    has_serp_data = bool(brief.serp_data_json)

    return ResearchBriefResponse(
        id=brief.id,
        agency_id=brief.agency_id,
        client_id=brief.client_id,
        client_name=client_name,
        competitor_id=brief.competitor_id,
        competitor_name=brief.competitor_name,
        brief_text=brief.brief_text,
        key_findings=key_findings,
        meta_ad_count=meta_ad_count,
        has_serp_data=has_serp_data,
        qdrant_point_id=brief.qdrant_point_id,
        acted_on=brief.acted_on,
        created_at=brief.created_at,
    )


# ── Competitors: Add ─────────────────────────────────────────────────────────

@router.post("/competitors", response_model=TrackedCompetitorResponse, status_code=201)
async def add_competitor(
    body: TrackedCompetitorCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M6],
) -> TrackedCompetitorResponse:
    """Owner adds a competitor to track for a specific client."""
    await _get_client(body.client_id, current_user.agency_id, db)

    # Check duplicate
    existing = await db.execute(
        select(TrackedCompetitor).where(
            TrackedCompetitor.client_id == body.client_id,
            TrackedCompetitor.competitor_name == body.competitor_name,
            TrackedCompetitor.agency_id == current_user.agency_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            409,
            f"Already tracking '{body.competitor_name}' for this client",
        )

    competitor = TrackedCompetitor(
        agency_id=current_user.agency_id,
        client_id=body.client_id,
        competitor_name=body.competitor_name,
        domain=body.domain,
        meta_page_id=body.meta_page_id,
        industry=body.industry,
        is_active=True,
    )
    db.add(competitor)
    await db.commit()
    await db.refresh(competitor)
    return await _build_competitor_response(competitor, db)


# ── Competitors: List ────────────────────────────────────────────────────────

@router.get(
    "/competitors/{client_id}",
    response_model=list[TrackedCompetitorResponse],
)
async def list_competitors(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M6],
) -> list[TrackedCompetitorResponse]:
    """Lists all tracked competitors for a client."""
    await _get_client(client_id, current_user.agency_id, db)

    result = await db.execute(
        select(TrackedCompetitor).where(
            TrackedCompetitor.client_id == client_id,
            TrackedCompetitor.agency_id == current_user.agency_id,
            TrackedCompetitor.is_active.is_(True),
        ).order_by(TrackedCompetitor.created_at.desc())
    )
    competitors = result.scalars().all()

    return [await _build_competitor_response(c, db) for c in competitors]


# ── Competitors: Remove ──────────────────────────────────────────────────────

@router.delete("/competitors/{competitor_id}", status_code=204)
async def remove_competitor(
    competitor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M6],
) -> None:
    """Soft delete — stops tracking competitor, keeps historical briefs."""
    result = await db.execute(
        select(TrackedCompetitor).where(
            TrackedCompetitor.id == competitor_id,
            TrackedCompetitor.agency_id == current_user.agency_id,
        )
    )
    competitor = result.scalar_one_or_none()
    if not competitor:
        raise HTTPException(404, "Competitor not found")

    competitor.is_active = False
    await db.commit()


# ── Research: Manual trigger ─────────────────────────────────────────────────

@router.post("/research/run", status_code=202)
async def run_research(
    body: ResearchRunRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M6],
) -> dict:
    """
    Owner manually triggers research for a client's competitors.
    If competitor_ids is None, runs for all active tracked competitors.
    Returns 202 — briefs appear in /m6/research/briefs after ~1 minute.
    """
    client = await _get_client(body.client_id, current_user.agency_id, db)

    # Fetch competitors to run
    query = select(TrackedCompetitor).where(
        TrackedCompetitor.client_id == body.client_id,
        TrackedCompetitor.agency_id == current_user.agency_id,
        TrackedCompetitor.is_active.is_(True),
    )
    if body.competitor_ids:
        query = query.where(
            TrackedCompetitor.id.in_(body.competitor_ids)
        )
    result = await db.execute(query)
    competitors = result.scalars().all()

    if not competitors:
        raise HTTPException(
            404,
            "No tracked competitors found for this client. "
            "Add competitors via POST /m6/competitors first.",
        )

    # Create brief records and run agents
    brief_records = []
    for comp in competitors:
        brief = ResearchBrief(
            agency_id=current_user.agency_id,
            client_id=comp.client_id,
            competitor_id=comp.id,
            competitor_name=comp.competitor_name,
        )
        db.add(brief)
        await db.flush()
        brief_records.append((comp, str(brief.id)))

    await db.commit()

    async def _run_all():
        from app.modules.m6_research.agent import run_research_agent
        for comp, brief_id in brief_records:
            try:
                await run_research_agent(
                    brief_id=brief_id,
                    agency_id=str(current_user.agency_id),
                    client_id=str(comp.client_id),
                    client_name=client.company_name,
                    competitor_id=str(comp.id),
                    competitor_name=comp.competitor_name,
                    meta_page_id=comp.meta_page_id,
                    domain=comp.domain,
                    industry=comp.industry,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    "Research failed for %s: %s",
                    comp.competitor_name, e,
                )

    background_tasks.add_task(_run_all)

    return {
        "status": "research_started",
        "client": client.company_name,
        "competitors": [c.competitor_name for c, _ in brief_records],
        "brief_count": len(brief_records),
        "message": (
            f"Researching {len(brief_records)} competitor(s). "
            f"Check /m6/research/briefs in ~1 minute."
        ),
    }


# ── Briefs: List ─────────────────────────────────────────────────────────────

@router.get("/research/briefs", response_model=list[ResearchBriefSummary])
async def list_briefs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M6],
    client_id: uuid.UUID | None = Query(None),
    acted_on: bool | None = Query(None),
) -> list[ResearchBriefSummary]:
    """
    Owner's research feed — all competitive intelligence briefs.
    Filter by client or acted_on status.
    Sorted newest first.
    """
    query = select(ResearchBrief).where(
        ResearchBrief.agency_id == current_user.agency_id,
        ResearchBrief.brief_text.is_not(None),  # only completed briefs
    )
    if client_id:
        query = query.where(ResearchBrief.client_id == client_id)
    if acted_on is not None:
        query = query.where(ResearchBrief.acted_on.is_(acted_on))

    query = query.order_by(ResearchBrief.created_at.desc())

    result = await db.execute(query)
    briefs = result.scalars().all()

    summaries = []
    for b in briefs:
        client_result = await db.execute(
            select(Client).where(Client.id == b.client_id)
        )
        client = client_result.scalar_one_or_none()

        try:
            key_findings = json.loads(b.key_findings_json)
        except Exception:
            key_findings = []

        summaries.append(ResearchBriefSummary(
            id=b.id,
            client_id=b.client_id,
            client_name=client.company_name if client else "Unknown",
            competitor_name=b.competitor_name,
            key_findings=key_findings,
            acted_on=b.acted_on,
            created_at=b.created_at,
        ))

    return summaries


# ── Briefs: Get one ──────────────────────────────────────────────────────────

@router.get("/research/briefs/{brief_id}", response_model=ResearchBriefResponse)
async def get_brief(
    brief_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M6],
) -> ResearchBriefResponse:
    result = await db.execute(
        select(ResearchBrief).where(
            ResearchBrief.id == brief_id,
            ResearchBrief.agency_id == current_user.agency_id,
        )
    )
    brief = result.scalar_one_or_none()
    if not brief:
        raise HTTPException(404, "Brief not found")

    return await _build_brief_response(brief, db)


# ── Briefs: Mark acted on ─────────────────────────────────────────────────────

@router.patch("/research/briefs/{brief_id}/act", response_model=ResearchBriefResponse)
async def mark_brief_acted_on(
    brief_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M6],
) -> ResearchBriefResponse:
    """Owner marks a brief as acted on after taking action."""
    result = await db.execute(
        select(ResearchBrief).where(
            ResearchBrief.id == brief_id,
            ResearchBrief.agency_id == current_user.agency_id,
        )
    )
    brief = result.scalar_one_or_none()
    if not brief:
        raise HTTPException(404, "Brief not found")

    brief.acted_on = True
    await db.commit()
    await db.refresh(brief)
    return await _build_brief_response(brief, db)


# ── Semantic search across briefs ─────────────────────────────────────────────

@router.get("/research/search", response_model=list[dict])
async def search_briefs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, M6],
    query: str = Query(..., min_length=3),
    client_id: uuid.UUID | None = Query(None),
    top_k: int = Query(default=5, ge=1, le=20),
) -> list[dict]:
    """
    Semantic search across all stored research briefs using Qdrant.
    Returns the most relevant competitive intelligence for your query.

    Example queries:
      - "video ad strategy"
      - "discount and offer messaging"
      - "competitor increasing spend"
    """
    from app.core.vector_store import search_similar, RESEARCH_COLLECTION

    filter_payload = {
        "must": [
            {
                "key": "agency_id",
                "match": {"value": str(current_user.agency_id)},
            }
        ]
    }

    if client_id:
        filter_payload["must"].append({
            "key": "client_id",
            "match": {"value": str(client_id)},
        })

    results = await search_similar(
        collection_name=RESEARCH_COLLECTION,
        query_text=query,
        top_k=top_k,
        filter_payload=filter_payload,
    )

    return [
        {
            "score": r["score"],
            "competitor_name": r["payload"].get("competitor_name"),
            "client_name": r["payload"].get("client_name"),
            "key_findings": r["payload"].get("key_findings", []),
            "brief_preview": r["payload"].get("brief_preview", ""),
            "brief_id": r["payload"].get("brief_id"),
        }
        for r in results
    ]