"""Client portal — read-only view of a client's plan, topics and delivered articles.

Clients sign in with an emailed link (no passwords): the link carries a signed,
time-limited token for their email address. Everything a client can see is
keyed on that email matching `client_email` on a brand or submission.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from content_factory.plans import PLANS, get_plan, is_free

LOGIN_TOKEN_MAX_AGE = 30 * 60  # seconds
_SALT = "said-by-portal-login"

DAY_NAMES = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
             "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
WEEKDAYS = list(DAY_NAMES)


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


# ── Login tokens ─────────────────────────────────────────────────────────────
def make_login_token(email: str, secret: str) -> str:
    return URLSafeTimedSerializer(secret, salt=_SALT).dumps(normalize_email(email))


def read_login_token(token: str, secret: str, max_age: int = LOGIN_TOKEN_MAX_AGE) -> str | None:
    try:
        return URLSafeTimedSerializer(secret, salt=_SALT).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


# ── Lookups ──────────────────────────────────────────────────────────────────
def _load(path: Path) -> dict:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}


def brands_for_email(email: str, brands_dir: Path) -> list[dict]:
    email = normalize_email(email)
    if not email or not brands_dir.exists():
        return []
    out = []
    for p in sorted(brands_dir.glob("*.yaml")):
        b = _load(p)
        if normalize_email(b.get("client_email")) == email:
            out.append({**b, "brand_id": b.get("brand_id") or p.stem})
    return out


def open_submissions_for_email(email: str, submissions_dir: Path) -> list[dict]:
    """Submissions not yet turned into a brand (being reviewed / awaiting payment)."""
    email = normalize_email(email)
    if not email or not submissions_dir.exists():
        return []
    out = []
    for p in sorted(submissions_dir.glob("*.yaml"), reverse=True):
        s = _load(p)
        if normalize_email(s.get("client_email")) == email and s.get("status") != "activated":
            out.append(s)
    return out


def email_is_known(email: str, brands_dir: Path, submissions_dir: Path) -> bool:
    return bool(brands_for_email(email, brands_dir) or open_submissions_for_email(email, submissions_dir))


# ── View models ──────────────────────────────────────────────────────────────
def delivered_articles(brand_id: str, generated_dir: Path) -> list[dict]:
    d = generated_dir / brand_id
    if not d.exists():
        return []
    items = []
    for p in d.glob("*.yaml"):
        g = _load(p)
        if g.get("status") != "approved":
            continue
        items.append({
            "run_id": p.stem,
            "title": " ".join((g.get("topic") or "").split()),
            "date": str(g.get("generated_at") or p.stem[:10]),
            "type": "Short post" if g.get("slot_type") == "short_snippet" else "Long-form article",
        })
    return sorted(items, key=lambda a: (a["date"], a["run_id"]), reverse=True)


def article_for_client(brand_id: str, run_id: str, generated_dir: Path) -> dict | None:
    g = _load(generated_dir / brand_id / f"{run_id}.yaml")
    if g.get("status") != "approved":
        return None
    return {
        "run_id": run_id,
        "title": " ".join((g.get("topic") or "").split()),
        "date": str(g.get("generated_at") or run_id[:10]),
        "type": "Short post" if g.get("slot_type") == "short_snippet" else "Long-form article",
        "content": g.get("content") or "",
    }


def _next_publish_day(slots: list[dict], today_idx: int) -> str | None:
    for offset in range(1, 8):
        key = WEEKDAYS[(today_idx + offset) % 7]
        if any(s.get("day") == key for s in slots):
            return DAY_NAMES[key]
    return None


def brand_overview(brand: dict, topics_dir: Path, generated_dir: Path, today_idx: int) -> dict:
    brand_id = brand["brand_id"]
    plan_id = brand.get("plan") or ""
    plan = get_plan(plan_id)
    package_size = int(brand.get("package_size") or (plan or {}).get("articles") or 0)
    cadence = (brand.get("cadence") or {}).get("publication_cadence", "weekly")
    slots = brand.get("content_slots") or []

    topics_doc = _load(topics_dir / f"{brand_id}.yaml")
    topics_ready = topics_doc.get("status") == "approved"
    TOPIC_LABEL = {"sent": "Delivered", "generated": "Being finalised"}
    topics = [
        {"title": " ".join((t.get("title") or "").split()),
         "status": TOPIC_LABEL.get(t.get("status"), "Upcoming")}
        for t in topics_doc.get("topics", [])
    ] if topics_ready else []

    articles = delivered_articles(brand_id, generated_dir)
    delivered = len(articles)
    complete = package_size and delivered >= package_size

    if complete:
        stage = "complete"
    elif not topics_ready:
        stage = "preparing_topics"
    elif not brand.get("plan_confirmed"):
        stage = "awaiting_confirmation"
    else:
        stage = "in_progress"

    pay = brand.get("payment") or {}
    upgrade = brand.get("upgrade") or {}
    free = is_free(plan_id)
    return {
        "brand_id": brand_id,
        "client_name": brand.get("client_name") or "",
        "plan_id": plan_id,
        "plan_label": (plan or {}).get("label") or f"{package_size}-article plan",
        "is_free_preview": free,
        "package_size": package_size,
        "delivered": delivered,
        "cadence_label": "One article, then a short post the next week" if free
        else ("2× per week" if cadence == "twice_weekly" else "1× per week"),
        "publish_days": [DAY_NAMES.get(s.get("day"), s.get("day")) for s in slots],
        "next_publish_day": None if complete or stage != "in_progress" else _next_publish_day(slots, today_idx),
        "stage": stage,
        "payment_status": pay.get("status") or ("free" if free else ""),
        "upgrade_paid": bool(upgrade),
        "upgrade_plan_label": (get_plan(upgrade.get("plan")) or {}).get("label") if upgrade else None,
        "topics": topics,
        "articles": articles,
        "upgrade_options": [
            {"id": p["id"], "label": p["label"], "articles": p["articles"],
             "price_cents": p["price_cents"], "list_price_cents": p["list_price_cents"]}
            for p in PLANS.values() if not is_free(p["id"])
        ] if free and not upgrade else [],
    }


def submission_overview(sub: dict) -> dict:
    plan = get_plan(sub.get("plan")) or {}
    return {
        "id": sub.get("id"),
        "submitted_at": str(sub.get("submitted_at") or "")[:10],
        "plan_label": plan.get("label") or "",
        "status": sub.get("status"),
        "payment_status": (sub.get("payment") or {}).get("status", ""),
    }
