"""
Ad platform data fetchers for M3 Reporting Agent.

Each function returns a standardised metrics dict.
If credentials are missing or API call fails, returns
realistic stub data so the full report pipeline can
be tested without real API keys.

Real credential setup per platform:
  GA4          — Google service account JSON + property ID
  Meta Ads     — System user access token + ad account ID
  Google Ads   — Developer token + customer ID + OAuth refresh token
"""
import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


# ── Stub data factory ────────────────────────────────────────────────────────

def _meta_stub(period_start: datetime, period_end: datetime) -> dict:
    return {
        "platform": "meta",
        "period": f"{period_start.date()} to {period_end.date()}",
        "spend": 48500.00,
        "impressions": 285000,
        "clicks": 4200,
        "ctr": 1.47,
        "cpc": 11.55,
        "conversions": 142,
        "roas": 3.1,
        "top_campaign": "Summer Sale - Retargeting",
        "is_stub": True,
    }


def _ga4_stub(period_start: datetime, period_end: datetime) -> dict:
    return {
        "platform": "ga4",
        "period": f"{period_start.date()} to {period_end.date()}",
        "sessions": 12400,
        "users": 9800,
        "new_users": 6200,
        "bounce_rate": 42.3,
        "avg_session_duration_seconds": 187,
        "conversions": 89,
        "conversion_rate": 0.72,
        "top_channel": "Paid Social",
        "top_landing_page": "/summer-sale",
        "is_stub": True,
    }


def _google_ads_stub(period_start: datetime, period_end: datetime) -> dict:
    return {
        "platform": "google_ads",
        "period": f"{period_start.date()} to {period_end.date()}",
        "spend": 32000.00,
        "impressions": 198000,
        "clicks": 3100,
        "ctr": 1.57,
        "cpc": 10.32,
        "conversions": 98,
        "roas": 2.8,
        "top_campaign": "Brand Keywords - Exact",
        "quality_score_avg": 7.2,
        "is_stub": True,
    }


# ── GA4 Data Pull ────────────────────────────────────────────────────────────

async def fetch_ga4_data(
    property_id: str,
    access_token: str,
    period_start: datetime,
    period_end: datetime,
) -> dict:
    """
    Pulls sessions, users, bounce rate, conversions from GA4.
    Uses GA4 Data API v1beta.
    Returns stub if property_id or token missing.
    """
    if not property_id or not access_token:
        logger.warning("[GA4] No credentials — returning stub data")
        return _ga4_stub(period_start, period_end)

    start_str = period_start.strftime("%Y-%m-%d")
    end_str = period_end.strftime("%Y-%m-%d")

    body = {
        "dateRanges": [{"startDate": start_str, "endDate": end_str}],
        "metrics": [
            {"name": "sessions"},
            {"name": "totalUsers"},
            {"name": "newUsers"},
            {"name": "bounceRate"},
            {"name": "averageSessionDuration"},
            {"name": "conversions"},
            {"name": "sessionConversionRate"},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
                headers={"Authorization": f"Bearer {access_token}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        row = data.get("rows", [{}])[0]
        values = [v.get("value", "0") for v in row.get("metricValues", [])]

        return {
            "platform": "ga4",
            "period": f"{start_str} to {end_str}",
            "sessions": int(values[0]) if values else 0,
            "users": int(values[1]) if len(values) > 1 else 0,
            "new_users": int(values[2]) if len(values) > 2 else 0,
            "bounce_rate": round(float(values[3]) * 100, 2) if len(values) > 3 else 0,
            "avg_session_duration_seconds": round(float(values[4])) if len(values) > 4 else 0,
            "conversions": int(values[5]) if len(values) > 5 else 0,
            "conversion_rate": round(float(values[6]) * 100, 2) if len(values) > 6 else 0,
            "is_stub": False,
        }

    except Exception as e:
        logger.error("[GA4] API call failed: %s — returning stub", e)
        return _ga4_stub(period_start, period_end)


# ── Meta Ads Data Pull ───────────────────────────────────────────────────────

async def fetch_meta_data(
    ad_account_id: str,
    access_token: str,
    period_start: datetime,
    period_end: datetime,
) -> dict:
    """
    Pulls spend, impressions, clicks, CTR, CPC, conversions, ROAS from Meta.
    Uses Meta Marketing API v19.
    Returns stub if credentials missing.
    """
    if not ad_account_id or not access_token:
        logger.warning("[Meta] No credentials — returning stub data")
        return _meta_stub(period_start, period_end)

    start_str = period_start.strftime("%Y-%m-%d")
    end_str = period_end.strftime("%Y-%m-%d")

    params = {
        "fields": "spend,impressions,clicks,ctr,cpc,actions,action_values,purchase_roas",
        "time_range": f'{{"since":"{start_str}","until":"{end_str}"}}',
        "access_token": access_token,
        "level": "account",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://graph.facebook.com/v19.0/act_{ad_account_id}/insights",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        d = data.get("data", [{}])[0] if data.get("data") else {}

        # Extract purchase conversions from actions array
        conversions = 0
        for action in d.get("actions", []):
            if action.get("action_type") == "purchase":
                conversions = int(action.get("value", 0))
                break

        # ROAS
        roas = 0.0
        for roas_entry in d.get("purchase_roas", []):
            roas = round(float(roas_entry.get("value", 0)), 2)
            break

        return {
            "platform": "meta",
            "period": f"{start_str} to {end_str}",
            "spend": round(float(d.get("spend", 0)), 2),
            "impressions": int(d.get("impressions", 0)),
            "clicks": int(d.get("clicks", 0)),
            "ctr": round(float(d.get("ctr", 0)), 2),
            "cpc": round(float(d.get("cpc", 0)), 2),
            "conversions": conversions,
            "roas": roas,
            "is_stub": False,
        }

    except Exception as e:
        logger.error("[Meta] API call failed: %s — returning stub", e)
        return _meta_stub(period_start, period_end)


# ── Google Ads Data Pull ─────────────────────────────────────────────────────

async def fetch_google_ads_data(
    customer_id: str,
    developer_token: str,
    access_token: str,
    period_start: datetime,
    period_end: datetime,
) -> dict:
    """
    Pulls spend, impressions, clicks, CTR, CPC, conversions from Google Ads.
    Uses Google Ads REST API (REST endpoint, no protobuf needed).
    Returns stub if credentials missing.
    """
    if not customer_id or not developer_token or not access_token:
        logger.warning("[Google Ads] No credentials — returning stub data")
        return _google_ads_stub(period_start, period_end)

    start_str = period_start.strftime("%Y-%m-%d")
    end_str = period_end.strftime("%Y-%m-%d")

    # GAQL query
    query = f"""
        SELECT
            metrics.cost_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.conversions
        FROM customer
        WHERE segments.date BETWEEN '{start_str}' AND '{end_str}'
    """

    clean_customer_id = customer_id.replace("-", "")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://googleads.googleapis.com/v16/customers/{clean_customer_id}/googleAds:search",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "developer-token": developer_token,
                },
                json={"query": query},
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        if not results:
            return _google_ads_stub(period_start, period_end)

        # Aggregate across all rows
        total_cost_micros = sum(
            int(r.get("metrics", {}).get("costMicros", 0)) for r in results
        )
        total_impressions = sum(
            int(r.get("metrics", {}).get("impressions", 0)) for r in results
        )
        total_clicks = sum(
            int(r.get("metrics", {}).get("clicks", 0)) for r in results
        )
        total_conversions = sum(
            float(r.get("metrics", {}).get("conversions", 0)) for r in results
        )

        spend = total_cost_micros / 1_000_000
        ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        cpc = (spend / total_clicks) if total_clicks > 0 else 0
        roas = 0.0  # Google Ads REST doesn't return ROAS directly without conv value

        return {
            "platform": "google_ads",
            "period": f"{start_str} to {end_str}",
            "spend": round(spend, 2),
            "impressions": total_impressions,
            "clicks": total_clicks,
            "ctr": round(ctr, 2),
            "cpc": round(cpc, 2),
            "conversions": int(total_conversions),
            "roas": roas,
            "is_stub": False,
        }

    except Exception as e:
        logger.error("[Google Ads] API call failed: %s — returning stub", e)
        return _google_ads_stub(period_start, period_end)


# ── Metrics processor ────────────────────────────────────────────────────────

def process_metrics(
    raw_metrics: dict,
    kpi_targets: dict | None = None,
) -> dict:
    """
    Takes raw per-platform metrics and produces a unified summary.
    Adds performance vs target flags for each KPI if targets provided.
    This processed dict is what Claude receives for narrative generation.
    """
    summary = {
        "platforms_included": list(raw_metrics.keys()),
        "total_spend": 0.0,
        "total_conversions": 0,
        "overall_roas": 0.0,
        "platforms": raw_metrics,
        "performance_flags": [],
        "has_stub_data": any(
            v.get("is_stub") for v in raw_metrics.values() if isinstance(v, dict)
        ),
    }

    # Aggregate across platforms
    total_spend = 0.0
    total_conversions = 0
    weighted_roas_sum = 0.0

    for platform, data in raw_metrics.items():
        if not isinstance(data, dict):
            continue
        spend = data.get("spend", 0) or 0
        conversions = data.get("conversions", 0) or 0
        roas = data.get("roas", 0) or 0

        total_spend += spend
        total_conversions += conversions
        weighted_roas_sum += roas * spend

    summary["total_spend"] = round(total_spend, 2)
    summary["total_conversions"] = total_conversions
    summary["overall_roas"] = (
        round(weighted_roas_sum / total_spend, 2) if total_spend > 0 else 0.0
    )

    # Flag performance vs targets
    if kpi_targets:
        target_roas = kpi_targets.get("roas")
        if target_roas and summary["overall_roas"] < float(target_roas):
            summary["performance_flags"].append(
                f"ROAS ({summary['overall_roas']}) is below target ({target_roas})"
            )

        for platform, data in raw_metrics.items():
            if not isinstance(data, dict):
                continue
            target_ctr = kpi_targets.get("ctr")
            if target_ctr and data.get("ctr", 0) < float(target_ctr):
                summary["performance_flags"].append(
                    f"{platform.upper()} CTR ({data.get('ctr')}%) below target ({target_ctr}%)"
                )

    return summary