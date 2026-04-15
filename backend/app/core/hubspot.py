"""
HubSpot CRM integration for M7 Lead Analyst Agent.

Used for:
  - Writing ICP score back to HubSpot deal/contact properties
  - Creating follow-up tasks on HubSpot for the AE
  - (M2 already handles inbound deal webhooks)

Requires HUBSPOT_ACCESS_TOKEN in .env.
All functions stub gracefully if token missing.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

HUBSPOT_API_BASE = "https://api.hubapi.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.hubspot_access_token}",
        "Content-Type": "application/json",
    }


async def update_contact_property(
    contact_id: str,
    properties: dict,
) -> bool:
    """
    Updates properties on a HubSpot contact.
    e.g. {"icp_score": "85", "icp_rationale": "Strong D2C fit..."}

    Returns True on success, False on failure.
    """
    if not settings.hubspot_access_token:
        logger.warning(
            "[HubSpot STUB] Would update contact %s: %s",
            contact_id,
            properties,
        )
        return True

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.patch(
                f"{HUBSPOT_API_BASE}/crm/v3/objects/contacts/{contact_id}",
                headers=_headers(),
                json={"properties": properties},
            )
            response.raise_for_status()
            return True
    except Exception as e:
        logger.error("[HubSpot] Contact update failed: %s", e)
        return False


async def update_deal_property(
    deal_id: str,
    properties: dict,
) -> bool:
    """Updates properties on a HubSpot deal."""
    if not settings.hubspot_access_token:
        logger.warning(
            "[HubSpot STUB] Would update deal %s: %s",
            deal_id,
            properties,
        )
        return True

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.patch(
                f"{HUBSPOT_API_BASE}/crm/v3/objects/deals/{deal_id}",
                headers=_headers(),
                json={"properties": properties},
            )
            response.raise_for_status()
            return True
    except Exception as e:
        logger.error("[HubSpot] Deal update failed: %s", e)
        return False


async def create_task(
    owner_id: str,
    subject: str,
    body: str,
    due_date_ms: int,
    associated_contact_id: str | None = None,
) -> str | None:
    """
    Creates a task in HubSpot for the AE.
    Returns the created task ID or None on failure.
    """
    if not settings.hubspot_access_token:
        logger.warning(
            "[HubSpot STUB] Would create task: %s",
            subject,
        )
        return "stub_task_id"

    payload = {
        "properties": {
            "hs_task_subject": subject,
            "hs_task_body": body,
            "hs_task_status": "NOT_STARTED",
            "hs_task_priority": "HIGH",
            "hs_timestamp": str(due_date_ms),
            "hubspot_owner_id": owner_id,
        }
    }

    if associated_contact_id:
        payload["associations"] = [
            {
                "to": {"id": associated_contact_id},
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": 204,
                    }
                ],
            }
        ]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{HUBSPOT_API_BASE}/crm/v3/objects/tasks",
                headers=_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json().get("id")
    except Exception as e:
        logger.error("[HubSpot] Task creation failed: %s", e)
        return None


async def get_deal(deal_id: str) -> dict:
    """Fetches deal details from HubSpot."""
    if not settings.hubspot_access_token:
        return {
            "id": deal_id,
            "properties": {
                "dealname": "Sample Deal",
                "amount": "500000",
                "hs_deal_stage": "closedwon",
            },
        }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{HUBSPOT_API_BASE}/crm/v3/objects/deals/{deal_id}",
                headers=_headers(),
                params={
                    "properties": "dealname,amount,hs_deal_stage,description"
                },
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("[HubSpot] Get deal failed: %s", e)
        return {}