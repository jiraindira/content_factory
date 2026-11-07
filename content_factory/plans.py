"""Plan catalogue — single source of truth for what clients can buy.

The intake form reads this via GET /api/plans, checkout charges from it, and
activation pre-fills package/cadence/slots from it. Change prices here only.
"""
from __future__ import annotations

PLANS: dict[str, dict] = {
    "free_preview": {
        "id": "free_preview",
        "label": "Free preview",
        "articles": 2,
        "price_cents": 0,
        "list_price_cents": 0,
        "blurb": "1 long article + 1 short post, a week apart. No card.",
        # Weekly, one slot; the slot type alternates long → short (see scheduler).
        "fixed_cadence": "weekly",
        "slot_type_sequence": ["long_blog", "short_snippet"],
    },
    "starter": {
        "id": "starter",
        "label": "Starter",
        "articles": 8,
        "price_cents": 4900,
        "list_price_cents": 9900,
        "blurb": "8 articles · 1×/week · about 2 months.",
        "default_cadence": "weekly",
    },
    "standard": {
        "id": "standard",
        "label": "Standard",
        "articles": 16,
        "price_cents": 8900,
        "list_price_cents": 13900,
        "blurb": "16 articles · 2×/week · about 2 months.",
        "default_cadence": "twice_weekly",
    },
    "premium": {
        "id": "premium",
        "label": "Premium",
        "articles": 24,
        "price_cents": 11900,
        "list_price_cents": 16900,
        "blurb": "24 articles · 2×/week · about 3 months.",
        "default_cadence": "twice_weekly",
    },
}

CADENCES = ("weekly", "twice_weekly")
CURRENCY = "usd"


def get_plan(plan_id: str | None) -> dict | None:
    return PLANS.get(plan_id or "")


def is_free(plan_id: str | None) -> bool:
    plan = get_plan(plan_id)
    return bool(plan) and plan["price_cents"] == 0


def public_catalogue() -> list[dict]:
    return [
        {k: v for k, v in p.items() if k != "slot_type_sequence"}
        for p in PLANS.values()
    ]
