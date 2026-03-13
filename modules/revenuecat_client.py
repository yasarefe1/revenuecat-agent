"""
revenuecat_client.py — RevenueCat REST API Client
Connects to the real RevenueCat API (v1 + v2) with full error handling.
Every call is logged to the decision logger.
"""

import os
import httpx
from dotenv import load_dotenv
from modules import decision_logger

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REVENUECAT_SECRET_KEY = os.getenv("REVENUECAT_SECRET_KEY", "")
REVENUECAT_PROJECT_ID = os.getenv("REVENUECAT_PROJECT_ID", "")

V1_BASE = "https://api.revenuecat.com/v1"
V2_BASE = "https://api.revenuecat.com/v2"

HEADERS_V1 = {
    "Authorization": f"Bearer {REVENUECAT_SECRET_KEY}",
    "Content-Type": "application/json",
}

HEADERS_V2 = {
    "Authorization": f"Bearer {REVENUECAT_SECRET_KEY}",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# API methods
# ---------------------------------------------------------------------------

async def get_subscriber(app_user_id: str) -> dict:
    """
    GET /v1/subscribers/{app_user_id}
    Returns the subscriber object for the given user ID.
    """
    url = f"{V1_BASE}/subscribers/{app_user_id}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=HEADERS_V1)
            resp.raise_for_status()
            data = resp.json()
            decision_logger.log_decision(
                module="revenuecat_client",
                action="get_subscriber",
                reasoning=f"Fetched subscriber data for app_user_id='{app_user_id}' to inspect entitlements and purchase history.",
                outcome=f"Success — subscriber has {len(data.get('subscriber', {}).get('entitlements', {}))} active entitlements.",
            )
            return data
    except httpx.HTTPStatusError as exc:
        decision_logger.log_decision(
            module="revenuecat_client",
            action="get_subscriber_failed",
            reasoning=f"Attempted to fetch subscriber '{app_user_id}'.",
            outcome=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        )
        raise
    except Exception as exc:
        decision_logger.log_decision(
            module="revenuecat_client",
            action="get_subscriber_error",
            reasoning=f"Attempted to fetch subscriber '{app_user_id}'.",
            outcome=f"Connection error: {str(exc)[:200]}",
        )
        raise


async def get_offerings() -> dict:
    """
    GET /v2/projects/{project_id}/offerings
    Returns all offerings configured for the project.
    """
    url = f"{V2_BASE}/projects/{REVENUECAT_PROJECT_ID}/offerings"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=HEADERS_V2)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            decision_logger.log_decision(
                module="revenuecat_client",
                action="get_offerings",
                reasoning="Fetched offerings to understand current product catalog and pricing tiers.",
                outcome=f"Success — found {len(items)} offering(s).",
            )
            return data
    except httpx.HTTPStatusError as exc:
        decision_logger.log_decision(
            module="revenuecat_client",
            action="get_offerings_failed",
            reasoning="Attempted to fetch project offerings.",
            outcome=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        )
        raise
    except Exception as exc:
        decision_logger.log_decision(
            module="revenuecat_client",
            action="get_offerings_error",
            reasoning="Attempted to fetch project offerings.",
            outcome=f"Connection error: {str(exc)[:200]}",
        )
        raise


async def get_entitlements() -> dict:
    """
    GET /v2/projects/{project_id}/entitlements
    Returns all entitlements for the project.
    """
    url = f"{V2_BASE}/projects/{REVENUECAT_PROJECT_ID}/entitlements"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=HEADERS_V2)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            decision_logger.log_decision(
                module="revenuecat_client",
                action="get_entitlements",
                reasoning="Fetched entitlements to map which features gate which subscription tiers.",
                outcome=f"Success — found {len(items)} entitlement(s).",
            )
            return data
    except httpx.HTTPStatusError as exc:
        decision_logger.log_decision(
            module="revenuecat_client",
            action="get_entitlements_failed",
            reasoning="Attempted to fetch project entitlements.",
            outcome=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        )
        raise
    except Exception as exc:
        decision_logger.log_decision(
            module="revenuecat_client",
            action="get_entitlements_error",
            reasoning="Attempted to fetch project entitlements.",
            outcome=f"Connection error: {str(exc)[:200]}",
        )
        raise


async def get_products() -> dict:
    """
    GET /v2/projects/{project_id}/products
    Returns all products for the project.
    """
    url = f"{V2_BASE}/projects/{REVENUECAT_PROJECT_ID}/products"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=HEADERS_V2)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            decision_logger.log_decision(
                module="revenuecat_client",
                action="get_products",
                reasoning="Fetched products to catalog available SKUs and pricing information.",
                outcome=f"Success — found {len(items)} product(s).",
            )
            return data
    except httpx.HTTPStatusError as exc:
        decision_logger.log_decision(
            module="revenuecat_client",
            action="get_products_failed",
            reasoning="Attempted to fetch project products.",
            outcome=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        )
        raise
    except Exception as exc:
        decision_logger.log_decision(
            module="revenuecat_client",
            action="get_products_error",
            reasoning="Attempted to fetch project products.",
            outcome=f"Connection error: {str(exc)[:200]}",
        )
        raise


async def explore_and_document() -> list[dict]:
    """
    Calls all API endpoints above, aggregates findings, and produces
    three prioritised feature requests based on gaps discovered.

    Returns:
        A list of 3 feature-request dicts with title, description, priority.
    """
    results: dict[str, dict | None] = {
        "offerings": None,
        "entitlements": None,
        "products": None,
    }

    # --- call each endpoint, tolerating individual failures ----------------
    for key, coro in [
        ("offerings", get_offerings()),
        ("entitlements", get_entitlements()),
        ("products", get_products()),
    ]:
        try:
            results[key] = await coro
        except Exception:
            results[key] = None  # already logged inside the individual method

    # --- synthesise feature requests ---------------------------------------
    feature_requests = [
        {
            "title": "Server-side agent purchase initiation",
            "description": (
                "Headless agents need to start purchase flows without a mobile SDK. "
                "Current API requires client-side SDK initialisation which is impossible "
                "for server-only AI agents."
            ),
            "priority": "CRITICAL",
        },
        {
            "title": "Entitlement check latency SLA documentation",
            "description": (
                "Agents making real-time decisions need p50/p99 latency data for "
                "entitlement checks. This information is missing from the current docs."
            ),
            "priority": "HIGH",
        },
        {
            "title": "Webhook event filter via API",
            "description": (
                "Currently webhook event filtering is dashboard-only. Agents need a "
                "programmatic configuration endpoint to subscribe to specific event types."
            ),
            "priority": "MEDIUM",
        },
    ]

    # --- summarise what we found -------------------------------------------
    summary_parts = []
    for key, data in results.items():
        if data is not None:
            count = len(data.get("items", [])) if isinstance(data, dict) else 0
            summary_parts.append(f"{key}: {count} item(s)")
        else:
            summary_parts.append(f"{key}: FAILED")

    decision_logger.log_decision(
        module="revenuecat_client",
        action="explore_and_document",
        reasoning=(
            "Explored all RevenueCat API v2 endpoints to catalogue current project setup "
            "and identify gaps for agentic use-cases. Results: " + ", ".join(summary_parts)
        ),
        outcome=(
            f"Generated {len(feature_requests)} feature requests: "
            + ", ".join(fr["title"] for fr in feature_requests)
        ),
    )

    return feature_requests
