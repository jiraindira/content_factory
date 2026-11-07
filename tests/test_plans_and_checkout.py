"""Plans, free preview, and Stripe checkout flow (Stripe calls are stubbed)."""
from __future__ import annotations

import yaml
import pytest
from fastapi.testclient import TestClient

import onboarding_app
import scheduler
from content_factory import billing, emailer
from content_factory.plans import PLANS, is_free

FORM = {
    "client_name": "Ada Test", "client_email": "ada@example.com", "about": "Leadership",
    "core_beliefs": "x", "formative_experiences": "y", "audience_context": "z",
    "tone": "warm_reflective", "platform": "both",
    "personal_presence": "insight_only", "commercial_stance": "invisible",
}


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    subs, brands = tmp_path / "submissions", tmp_path / "brands"
    brands.mkdir()
    monkeypatch.setattr(onboarding_app, "SUBMISSIONS_DIR", subs)
    monkeypatch.setattr(onboarding_app, "BRANDS_DIR", brands)
    monkeypatch.setattr(onboarding_app, "_sync", lambda *a, **k: None)
    sent = []
    monkeypatch.setattr(emailer, "send_new_submission_email", lambda submission: sent.append(submission))
    monkeypatch.setattr(emailer, "send_upgrade_paid_email", lambda brand: sent.append(brand))
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    return TestClient(onboarding_app.app), subs, brands, sent


def _sub(subs, sub_id):
    return yaml.safe_load((subs / f"{sub_id}.yaml").read_text(encoding="utf-8"))


def test_plan_catalogue():
    assert PLANS["free_preview"]["articles"] == 2 and is_free("free_preview")
    assert PLANS["free_preview"]["slot_type_sequence"] == ["long_blog", "short_snippet"]
    assert not is_free("starter") and PLANS["starter"]["price_cents"] == 4900


def test_free_preview_once_per_email(app_env):
    client, subs, _, sent = app_env
    r = client.post("/api/submissions", json={**FORM, "plan": "free_preview", "cadence": "twice_weekly"})
    assert r.status_code == 200 and r.json()["checkout_url"] is None
    sub = _sub(subs, r.json()["id"])
    assert sub["cadence"] == "weekly"  # free preview is fixed weekly
    assert sub["payment"]["status"] == "free" and sub["status"] == "submitted"
    assert len(sent) == 1

    again = client.post("/api/submissions", json={**FORM, "client_email": "ADA@example.com ", "plan": "free_preview"})
    assert again.status_code == 409


def test_paid_plan_without_stripe_falls_back_to_offline(app_env):
    client, subs, _, sent = app_env
    r = client.post("/api/submissions", json={**FORM, "plan": "standard"})
    sub = _sub(subs, r.json()["id"])
    assert sub["payment"]["status"] == "offline" and sub["status"] == "submitted"
    assert sub["cadence"] == "twice_weekly"  # plan default
    assert len(sent) == 1


def test_unknown_plan_rejected(app_env):
    client, *_ = app_env
    assert client.post("/api/submissions", json={**FORM, "plan": "gold"}).status_code == 400


def test_paid_checkout_then_confirm(app_env, monkeypatch):
    client, subs, _, sent = app_env
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    created = {}

    def fake_create(**kw):
        created.update(kw)
        return {"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/cs_test_123"}

    monkeypatch.setattr(billing, "create_checkout_session", fake_create)
    r = client.post("/api/submissions", json={**FORM, "plan": "starter", "cadence": "weekly"})
    body = r.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.com")
    assert created["plan_id"] == "starter" and created["metadata"] == {"submission_id": body["id"]}
    assert _sub(subs, body["id"])["status"] == "awaiting_payment"
    assert sent == []  # operator not emailed until paid

    session = {
        "id": "cs_test_123", "payment_status": "paid", "amount_total": 3900, "currency": "usd",
        "total_details": {"amount_discount": 1000}, "metadata": {"submission_id": body["id"]},
        "customer_details": {"email": "ada@example.com"},
    }
    monkeypatch.setattr(billing, "retrieve_session", lambda sid: session)
    c = client.post("/api/checkout/confirm", json={"session_id": "cs_test_123"})
    assert c.json() == {"paid": True, "kind": "submission"}
    sub = _sub(subs, body["id"])
    assert sub["status"] == "submitted"
    assert sub["payment"]["status"] == "paid" and sub["payment"]["discount_cents"] == 1000
    assert len(sent) == 1

    # Idempotent: webhook arriving after the success page doesn't re-notify.
    client.post("/api/checkout/confirm", json={"session_id": "cs_test_123"})
    assert len(sent) == 1


def test_confirm_rejects_unpaid_and_bad_ids(app_env, monkeypatch):
    client, *_ = app_env
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    assert client.post("/api/checkout/confirm", json={"session_id": "nope"}).status_code == 400
    monkeypatch.setattr(billing, "retrieve_session", lambda sid: {"payment_status": "unpaid", "metadata": {}})
    assert client.post("/api/checkout/confirm", json={"session_id": "cs_x"}).json() == {"paid": False}


def test_scheduler_alternates_free_preview_slot_type(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "TOPICS_DIR", tmp_path)
    brand = {"brand_id": "b", "slot_type_sequence": ["long_blog", "short_snippet"]}
    slot = {"day": "mon", "type": "long_blog"}

    def topics(statuses):
        (tmp_path / "b.yaml").write_text(yaml.dump({"topics": [{"status": s} for s in statuses]}), encoding="utf-8")

    topics(["approved", "approved"])
    assert scheduler._slot_type(brand, slot) == "long_blog"
    topics(["sent", "approved"])
    assert scheduler._slot_type(brand, slot) == "short_snippet"
    assert scheduler._slot_type({"brand_id": "b"}, {"type": "short_snippet"}) == "short_snippet"
