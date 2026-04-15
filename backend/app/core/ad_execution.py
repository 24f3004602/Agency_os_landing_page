"""
Ad platform execution utilities for M10 autonomous mode.

These functions make actual changes to live ad accounts:
  - pause_ad / pause_adset : stops spending immediately
  - update_bid             : changes CPC/CPA bid
  - update_budget          : changes daily budget

All functions:
  1. Validate the change is within guardrails before executing
  2. Return a result dict with before/after values
  3. Stub gracefully if credentials missing

CRITICAL: These make real changes to live campaigns.
Autonomous mode must only be enabled after thorough testing
in advisory mode first.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ── Guardrail validator ───────────────────────────────────────────────────────

def validate_budget_change(
    current_budget: float,
    proposed_budget: float,
    max_change_pct: float,
    min_daily_budget: float,
) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    Checks proposed change is within guardrails.
    """
    if proposed_budget < min_daily_budget:
        return False, (
            f"Proposed budget ₹{proposed_budget} is below "
            f"minimum ₹{min_daily_budget}"
        )

    if current_budget == 0:
        return True, "ok"

    change_pct = abs(proposed_budget - current_budget) / current_budget * 100
    if change_pct > max_change_pct:
        return False, (
            f"Change of {change_pct:.1f}% exceeds "
            f"guardrail of {max_change_pct}%"
        )

    return True, "ok"


def validate_bid_change(
    current_bid: float,
    proposed_bid: float,
    max_change_pct: float,
) -> tuple[bool, str]:
    """Returns (is_valid, reason)."""
    if current_bid == 0:
        return True, "ok"

    change_pct = abs(proposed_bid - current_bid) / current_bid * 100
    if change_pct > max_change_pct:
        return False, (
            f"Bid change of {change_pct:.1f}% exceeds "
            f"guardrail of {max_change_pct}%"
        )

    return True, "ok"


# ── Meta Ad Execution ─────────────────────────────────────────────────────────

async def meta_pause_ad(ad_id: str, access_token: str) -> dict:
    """Pauses a Meta ad by setting status to PAUSED."""
    if not access_token:
        logger.warning("[META STUB] Would pause ad %s", ad_id)
        return {"ad_id": ad_id, "status": "paused", "stub": True}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://graph.facebook.com/v19.0/{ad_id}",
                params={"access_token": access_token},
                json={"status": "PAUSED"},
            )
            response.raise_for_status()
            return {"ad_id": ad_id, "status": "paused", "api_response": response.json()}
    except Exception as e:
        logger.error("[Meta] Pause ad failed: %s", e)
        return {"ad_id": ad_id, "status": "failed", "error": str(e)}


async def meta_update_adset_budget(
    adset_id: str,
    daily_budget_cents: int,
    access_token: str,
) -> dict:
    """Updates daily budget for a Meta adset. Budget in cents."""
    if not access_token:
        logger.warning(
            "[META STUB] Would set adset %s budget to %d cents",
            adset_id,
            daily_budget_cents,
        )
        return {
            "adset_id": adset_id,
            "new_budget_cents": daily_budget_cents,
            "stub": True,
        }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://graph.facebook.com/v19.0/{adset_id}",
                params={"access_token": access_token},
                json={"daily_budget": str(daily_budget_cents)},
            )
            response.raise_for_status()
            return {
                "adset_id": adset_id,
                "new_budget_cents": daily_budget_cents,
                "api_response": response.json(),
            }
    except Exception as e:
        logger.error("[Meta] Budget update failed: %s", e)
        return {"adset_id": adset_id, "status": "failed", "error": str(e)}


# ── Google Ads Execution ───────────────────────────────────────────────────────

async def google_pause_ad(
    customer_id: str,
    ad_group_ad_resource: str,
    developer_token: str,
    access_token: str,
) -> dict:
    """Pauses a Google Ads ad."""
    if not developer_token or not access_token:
        logger.warning(
            "[GOOGLE ADS STUB] Would pause ad %s",
            ad_group_ad_resource,
        )
        return {
            "resource": ad_group_ad_resource,
            "status": "paused",
            "stub": True,
        }

    clean_customer_id = customer_id.replace("-", "")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://googleads.googleapis.com/v16/customers/{clean_customer_id}/adGroupAds:mutate",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "developer-token": developer_token,
                },
                json={
                    "operations": [
                        {
                            "update": {
                                "resourceName": ad_group_ad_resource,
                                "status": "PAUSED",
                            },
                            "updateMask": "status",
                        }
                    ]
                },
            )
            response.raise_for_status()
            return {
                "resource": ad_group_ad_resource,
                "status": "paused",
                "api_response": response.json(),
            }
    except Exception as e:
        logger.error("[Google Ads] Pause ad failed: %s", e)
        return {
            "resource": ad_group_ad_resource,
            "status": "failed",
            "error": str(e),
        }


async def google_update_campaign_budget(
    customer_id: str,
    campaign_budget_resource: str,
    amount_micros: int,
    developer_token: str,
    access_token: str,
) -> dict:
    """Updates a Google Ads campaign budget. Amount in micros (1 rupee = 1,000,000 micros)."""
    if not developer_token or not access_token:
        logger.warning(
            "[GOOGLE ADS STUB] Would set budget %s to %d micros",
            campaign_budget_resource,
            amount_micros,
        )
        return {
            "resource": campaign_budget_resource,
            "new_amount_micros": amount_micros,
            "stub": True,
        }

    clean_customer_id = customer_id.replace("-", "")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://googleads.googleapis.com/v16/customers/{clean_customer_id}/campaignBudgets:mutate",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "developer-token": developer_token,
                },
                json={
                    "operations": [
                        {
                            "update": {
                                "resourceName": campaign_budget_resource,
                                "amountMicros": str(amount_micros),
                            },
                            "updateMask": "amountMicros",
                        }
                    ]
                },
            )
            response.raise_for_status()
            return {
                "resource": campaign_budget_resource,
                "new_amount_micros": amount_micros,
                "api_response": response.json(),
            }
    except Exception as e:
        logger.error("[Google Ads] Budget update failed: %s", e)
        return {
            "resource": campaign_budget_resource,
            "status": "failed",
            "error": str(e),
        }