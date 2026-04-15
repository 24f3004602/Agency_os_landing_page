"""
WATI API integration for WhatsApp messaging.
Handles sending template and session messages to clients.

If WATI_API_KEY is empty in .env, send() logs a warning
and skips the actual API call — message still written to DB.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def send_whatsapp_message(
    phone_number: str,   # E.164 format: +919876543210
    message: str,
) -> dict:
    """
    Sends a WhatsApp message via WATI session message API.
    Phone must be in active session (client messaged first within 24h)
    or use a pre-approved template.

    Returns WATI response dict.
    Raises httpx.HTTPStatusError on API failure.
    """
    if not settings.wati_api_key or not settings.wati_base_url:
        logger.warning(
            "[WATI STUB] Would send to %s: %s",
            phone_number,
            message[:80],
        )
        return {"id": "stub", "status": "stub"}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.wati_base_url}/api/v1/sendSessionMessage/{phone_number}",
            headers={
                "Authorization": f"Bearer {settings.wati_api_key}",
                "Content-Type": "application/json",
            },
            json={"messageText": message},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()