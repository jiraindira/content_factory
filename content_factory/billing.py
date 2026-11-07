"""Stripe Checkout integration.

We use hosted Checkout in one-off `payment` mode with inline `price_data`, so the
only Stripe setup needed is two env vars:

  STRIPE_SECRET_KEY      sk_test_… (test mode) or sk_live_…
  STRIPE_WEBHOOK_SECRET  whsec_… for the /api/stripe/webhook endpoint

Coupons: `allow_promotion_codes=True` shows a "Add promotion code" box on
Stripe's page. Create coupons + promotion codes in the Stripe dashboard —
no coupon logic lives in this app.

If STRIPE_SECRET_KEY is unset, `enabled()` is False and the intake falls back
to "payment handled offline" so the site keeps working.
"""
from __future__ import annotations

import os

from content_factory.plans import CURRENCY, get_plan


def _key() -> str:
    return os.environ.get("STRIPE_SECRET_KEY", "").strip()


def enabled() -> bool:
    return bool(_key())


def _stripe():
    import stripe

    stripe.api_key = _key()
    return stripe


def create_checkout_session(
    *,
    plan_id: str,
    cadence: str,
    customer_email: str,
    base_url: str,
    metadata: dict,
    cancel_path: str = "/onboard",
) -> dict:
    """Create a hosted Checkout Session. Returns {"id", "url"}."""
    plan = get_plan(plan_id)
    if not plan or plan["price_cents"] <= 0:
        raise ValueError(f"Plan {plan_id!r} is not a paid plan")

    cadence_label = "2× per week" if cadence == "twice_weekly" else "1× per week"
    base = base_url.rstrip("/")
    sep = "&" if "?" in cancel_path else "?"
    session = _stripe().checkout.Session.create(
        mode="payment",
        customer_email=customer_email or None,
        client_reference_id=metadata.get("submission_id") or metadata.get("brand_id"),
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": CURRENCY,
                "unit_amount": plan["price_cents"],
                "product_data": {
                    "name": f"Said By — {plan['label']} ({plan['articles']} articles)",
                    "description": f"{plan['articles']} articles in your voice, {cadence_label}.",
                },
            },
        }],
        allow_promotion_codes=True,
        metadata={**metadata, "plan": plan_id, "cadence": cadence},
        success_url=f"{base}/onboard?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base}{cancel_path}{sep}cancelled=1",
    )
    return {"id": session["id"], "url": session["url"]}


def retrieve_session(session_id: str) -> dict:
    return _stripe().checkout.Session.retrieve(session_id)


def parse_webhook(payload: bytes, sig_header: str) -> dict:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET is not set")
    return _stripe().Webhook.construct_event(payload, sig_header, secret)


def payment_record(session: dict) -> dict:
    """The bits of a completed session we store on the submission/brand."""
    details = session.get("total_details") or {}
    return {
        "status": "paid",
        "provider": "stripe",
        "session_id": session.get("id"),
        "amount_total_cents": session.get("amount_total"),
        "discount_cents": details.get("amount_discount") or 0,
        "currency": session.get("currency"),
        "customer_email": (session.get("customer_details") or {}).get("email")
        or session.get("customer_email"),
    }
