"""
Competitor intelligence data fetchers for M6.

Sources:
  1. Meta Ad Library API — public endpoint, no auth required
     Shows active ads for any Facebook/Instagram page
  2. SerpAPI — paid API, shows Google search results
     Returns organic rankings, paid ads, competitor snippets

Both return stub data if credentials/IDs missing.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

META_AD_LIBRARY_URL = "https://graph.facebook.com/v19.0/ads_archive"


# ── Meta Ad Library ──────────────────────────────────────────────────────────

async def fetch_meta_ads(
    page_id: str,
    access_token: str | None = None,
) -> dict:
    """
    Fetches active ads for a Facebook/Instagram page
    from the Meta Ad Library (public API).

    page_id     : Facebook page ID of the competitor
    access_token: Optional — public queries work without it
                  but are rate-limited more aggressively

    Returns dict with ad count, sample ad texts, and spend ranges.
    """
    if not page_id:
        return _meta_stub(page_id)

    params = {
        "search_type": "ADVERTISER",
        "advertiser_page_ids": page_id,
        "ad_active_status": "ACTIVE",
        "fields": "id,ad_creative_bodies,ad_delivery_start_time,spend",
        "limit": 20,
    }

    if access_token:
        params["access_token"] = access_token

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(META_AD_LIBRARY_URL, params=params)
            response.raise_for_status()
            data = response.json()

        ads = data.get("data", [])

        ad_texts = []
        for ad in ads[:10]:
            bodies = ad.get("ad_creative_bodies", [])
            if bodies:
                ad_texts.append(bodies[0][:200])

        return {
            "source": "meta_ad_library",
            "page_id": page_id,
            "active_ad_count": len(ads),
            "sample_ad_texts": ad_texts,
            "is_stub": False,
        }

    except Exception as e:
        logger.warning(
            "[Meta Ad Library] Failed for page %s: %s — returning stub",
            page_id, e,
        )
        return _meta_stub(page_id)


def _meta_stub(page_id: str) -> dict:
    return {
        "source": "meta_ad_library",
        "page_id": page_id or "unknown",
        "active_ad_count": 12,
        "sample_ad_texts": [
            "🔥 Flat 40% off on all orders above ₹499! Order now →",
            "New arrivals just dropped. Shop the collection before it sells out.",
            "Free delivery on your first order. Use code: FIRST50",
        ],
        "is_stub": True,
    }


# ── SerpAPI ──────────────────────────────────────────────────────────────────

async def fetch_serp_data(
    competitor_name: str,
    domain: str | None = None,
    industry: str | None = None,
) -> dict:
    """
    Searches Google for the competitor and returns:
    - Organic ranking info
    - Active Google Ads (if any)
    - Recent news snippets

    Requires SERPAPI_KEY in .env.
    Returns stub if key missing.
    """
    serpapi_key = getattr(settings, "serpapi_key", "")

    if not serpapi_key:
        logger.warning(
            "[SerpAPI] No API key — returning stub for %s",
            competitor_name,
        )
        return _serp_stub(competitor_name, domain)

    query = f"{competitor_name} {industry or ''} ads campaigns".strip()

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": serpapi_key,
                    "engine": "google",
                    "num": 10,
                    "gl": "in",     # India results
                    "hl": "en",
                },
            )
            response.raise_for_status()
            data = response.json()

        # Extract organic results
        organic = data.get("organic_results", [])[:5]
        organic_snippets = [
            {
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
                "link": r.get("link", ""),
            }
            for r in organic
        ]

        # Extract paid ads
        ads = data.get("ads", [])[:3]
        paid_ads = [
            {
                "title": a.get("title", ""),
                "description": a.get("description", ""),
            }
            for a in ads
        ]

        # Knowledge graph (brand summary)
        kg = data.get("knowledge_graph", {})

        return {
            "source": "serpapi",
            "competitor_name": competitor_name,
            "organic_results": organic_snippets,
            "paid_ads": paid_ads,
            "knowledge_graph_description": kg.get("description", ""),
            "is_stub": False,
        }

    except Exception as e:
        logger.warning(
            "[SerpAPI] Failed for %s: %s — returning stub",
            competitor_name, e,
        )
        return _serp_stub(competitor_name, domain)


def _serp_stub(competitor_name: str, domain: str | None) -> dict:
    return {
        "source": "serpapi",
        "competitor_name": competitor_name,
        "domain": domain,
        "organic_results": [
            {
                "title": f"{competitor_name} — Official Website",
                "snippet": f"Discover {competitor_name}'s latest offers and products.",
                "link": f"https://{domain or 'example.com'}",
            },
        ],
        "paid_ads": [
            {
                "title": f"{competitor_name} — Up to 50% Off",
                "description": "Shop now and save big. Limited time offer.",
            }
        ],
        "knowledge_graph_description": (
            f"{competitor_name} is a leading brand in their category."
        ),
        "is_stub": True,
    }