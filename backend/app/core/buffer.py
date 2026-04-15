"""
Buffer REST API integration for social post scheduling.
Called when a campaign task is approved.

If BUFFER_ACCESS_TOKEN is not set in .env:
  - Logs a stub warning
  - Returns a fake post ID
  - Task still moves to 'scheduled' status

Real setup:
  1. Create a Buffer account
  2. Get access token from buffer.com/developers
  3. Add BUFFER_ACCESS_TOKEN and BUFFER_PROFILE_IDS to .env
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BUFFER_API_BASE = "https://api.bufferapp.com/1"


async def schedule_post(
    content: str,
    profile_id: str,         # Buffer profile ID (Facebook Page, Instagram, etc.)
    scheduled_at: str | None = None,  # ISO 8601 — None means add to queue
) -> dict:
    """
    Schedules a post via Buffer REST API.
    Returns Buffer's response dict including the post ID.

    Raises httpx.HTTPStatusError on API failure.
    """
    access_token = getattr(settings, "buffer_access_token", "")

    if not access_token:
        logger.warning(
            "[BUFFER STUB] Would schedule to profile %s: %s",
            profile_id,
            content[:80],
        )
        return {
            "id": f"stub_buffer_{profile_id[:8]}",
            "status": "buffer_stub",
            "profile_id": profile_id,
        }

    payload = {
        "text": content,
        "profile_ids[]": profile_id,
        "access_token": access_token,
    }

    if scheduled_at:
        payload["scheduled_at"] = scheduled_at

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{BUFFER_API_BASE}/updates/create.json",
            data=payload,
        )
        response.raise_for_status()
        return response.json()


async def get_post_status(post_id: str) -> dict:
    """
    Checks the status of a scheduled Buffer post.
    Used by M10 to detect when content goes live.
    """
    access_token = getattr(settings, "buffer_access_token", "")

    if not access_token or post_id.startswith("stub_"):
        return {"status": "stub", "id": post_id}

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{BUFFER_API_BASE}/updates/{post_id}.json",
            params={"access_token": access_token},
        )
        response.raise_for_status()
        return response.json()