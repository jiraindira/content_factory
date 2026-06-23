"""
Content Factory — API + UI server
Run locally: poetry run uvicorn onboarding_app:app --host localhost --port 8502 --reload
"""

import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import uvicorn
import yaml
import sys
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

# ── Config ────────────────────────────────────────────────────────────────────
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
SECRET_KEY     = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

BRANDS_DIR      = Path(__file__).parent / "content_factory" / "brands"
GENERATED_DIR   = Path(__file__).parent / "content_factory" / "generated"
TOPICS_DIR      = Path(__file__).parent / "content_factory" / "topics"
SUBMISSIONS_DIR = Path(__file__).parent / "content_factory" / "submissions"

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


# ── Auth helpers ──────────────────────────────────────────────────────────────
def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))

def api_auth(request: Request):
    """Dependency for API routes — returns 401 if not logged in."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")


# ── Public pages ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def homepage():
    return FileResponse(Path(__file__).parent / "index.html")

@app.get("/onboard", response_class=HTMLResponse)
def onboard_page():
    return FileResponse(Path(__file__).parent / "onboard.html")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=302)
    return FileResponse(Path(__file__).parent / "login.html")


# ── Auth actions ──────────────────────────────────────────────────────────────
@app.post("/auth/login")
async def do_login(request: Request):
    body = await request.json()
    if body.get("username") == ADMIN_USERNAME and body.get("password") == ADMIN_PASSWORD:
        request.session["authenticated"] = True
        return {"ok": True}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/auth/logout")
def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


# ── Admin page (protected) ────────────────────────────────────────────────────
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(Path(__file__).parent / "onboarding.html")


# ── Submissions (public write, admin read) ────────────────────────────────────
@app.post("/api/submissions")
async def create_submission(request: Request):
    data = await request.json()
    if not data.get("client_email"):
        raise HTTPException(status_code=400, detail="client_email is required")

    SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sub_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:6]
    data["id"] = sub_id
    data["submitted_at"] = datetime.utcnow().isoformat()
    data["status"] = "submitted"

    path = SUBMISSIONS_DIR / f"{sub_id}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    # Email operator
    try:
        from content_factory.emailer import send_new_submission_email
        send_new_submission_email(submission=data)
    except Exception as e:
        print(f"Warning: could not send submission email: {e}")

    return {"submitted": True, "id": sub_id}


@app.get("/api/submissions", dependencies=[Depends(api_auth)])
def list_submissions():
    if not SUBMISSIONS_DIR.exists():
        return []
    items = []
    for p in sorted(SUBMISSIONS_DIR.glob("*.yaml"), reverse=True):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        items.append({
            "id": data.get("id", p.stem),
            "client_name": data.get("client_name", ""),
            "client_email": data.get("client_email", ""),
            "brand_archetype": data.get("brand_archetype", ""),
            "submitted_at": data.get("submitted_at", ""),
            "status": data.get("status", "submitted"),
        })
    return items


@app.get("/api/submissions/{sub_id}", dependencies=[Depends(api_auth)])
def get_submission(sub_id: str):
    path = SUBMISSIONS_DIR / f"{sub_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Submission not found")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@app.post("/api/submissions/{sub_id}/activate", dependencies=[Depends(api_auth)])
async def activate_submission(sub_id: str, request: Request):
    """Convert a submission into a full brand profile."""
    path = SUBMISSIONS_DIR / f"{sub_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Submission not found")

    sub = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    body = await request.json()  # brand_id, package_size, publication_cadence, content_slots, time_zone

    brand_id = (body.get("brand_id") or "").strip()
    if not brand_id:
        raise HTTPException(status_code=400, detail="brand_id is required")

    # Map submission → brand profile fields
    tone = sub.get("tone", "practical_expert")
    presence_map = {
        "first_person_frequent":  ("first_person_preferred", "frequent_personal_anecdotes"),
        "first_person_occasional": ("first_person_allowed",  "occasional_personal_anecdotes"),
        "insight_only":           ("third_person_only",      "none"),
        "third_person":           ("third_person_only",      "none"),
    }
    narration, presence = presence_map.get(sub.get("personal_presence", "insight_only"), ("third_person_only", "none"))

    commercial_map = {
        "invisible":       ("invisible",            "none"),
        "soft_authority":  ("soft_recommendation",  "soft_authority_signature_line"),
        "gentle_cta":      ("clear_recommendation", "gentle_cta_at_end"),
        "clear_invitation":("explicit_cta",         "clear_invitation"),
    }
    comm_posture, cta_policy = commercial_map.get(sub.get("commercial_stance", "invisible"), ("invisible", "none"))

    platform_map = {
        "linkedin_only": (["social_longform"], ["linkedin"],                  "single_canonical_article"),
        "blog_only":     (["blog_article"],    ["hosted_by_us"],              "single_canonical_article"),
        "both":          (["blog_article", "social_longform"], ["hosted_by_us", "linkedin"], "canonical_plus_short_social"),
    }
    channels, destinations, strategy = platform_map.get(sub.get("platform", "both"),
        (["blog_article"], ["hosted_by_us"], "single_canonical_article"))

    domain = "leadership"  # default; operator can edit later

    persona_cfg = {
        "primary_persona": tone,
        "persona_modifiers": ["none"],
        "science_explicitness": sub.get("science_explicitness", "implied"),
        "personal_presence": presence,
        "narration_mode": narration,
    }

    cadence_val = body.get("publication_cadence", "weekly")
    slots = body.get("content_slots", [{"day": "mon", "type": "long_blog"}])
    publish_days = list({s["day"] for s in slots})

    brand = {
        "brand_id": brand_id,
        "client_name": sub.get("client_name", ""),
        "client_email": sub.get("client_email", ""),
        "brand_archetype": sub.get("brand_archetype", "mentor_coach"),
        "package_size": body.get("package_size", 8),
        "brand_sources": {
            "require_at_least_one_of_purposes": ["homepage"],
            "sources": [{"source_id": "homepage", "kind": "url", "purpose": "homepage", "ref": sub.get("website_url", "")}]
            if sub.get("website_url") else
            [{"source_id": "homepage", "kind": "url", "purpose": "homepage", "ref": "https://example.com"}],
        },
        "domains_supported": [domain],
        "domain_primary": domain,
        "audience": {
            "primary_audience": sub.get("audience", "general_consumers"),
            "audience_sophistication": "medium",
            "audience_context": sub.get("audience_context", ""),
        },
        "content_strategy": {
            "allowed_intents": ["thought_leadership"],
            "allowed_product_recommendation_forms": [],
            "allowed_thought_leadership_forms": [],
            "default_content_depth": "long",
        },
        "topic_policy": {"allowlist": [sub.get("about", "General")]},
        "persona_by_domain": {domain: persona_cfg},
        "commercial_policy": {
            "commercial_posture": comm_posture,
            "cta_policy": cta_policy,
            "prohibited_behaviors": ["fake_scarcity", "hype_superlatives", "pressure_language"],
        },
        "disclaimer_policy": {"required": False, "disclaimer_text": "", "locations": []},
        "delivery_policy": {
            "delivery_channels": channels,
            "delivery_destinations": destinations,
            "delivery_strategy": strategy,
            "auto_publish": False,
        },
        "cadence": {
            "publication_cadence": cadence_val,
            "preferred_publish_days": publish_days,
            "time_zone": body.get("time_zone", "UTC"),
        },
        "content_slots": slots,
    }

    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    brand_path = BRANDS_DIR / f"{brand_id}.yaml"
    with open(brand_path, "w", encoding="utf-8") as f:
        yaml.dump(brand, f, allow_unicode=True, sort_keys=False)

    # Mark submission as activated
    sub["status"] = "activated"
    sub["brand_id"] = brand_id
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(sub, f, allow_unicode=True, sort_keys=False)

    return {"activated": True, "brand_id": brand_id}


# ── Brands API (all admin-only) ───────────────────────────────────────────────
@app.get("/api/brands", dependencies=[Depends(api_auth)])
def list_brands():
    if not BRANDS_DIR.exists():
        return []
    return sorted(p.stem for p in BRANDS_DIR.glob("*.yaml"))


@app.get("/api/brands/{brand_id}", dependencies=[Depends(api_auth)])
def get_brand(brand_id: str):
    path = BRANDS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Brand not found")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@app.delete("/api/brands/{brand_id}", dependencies=[Depends(api_auth)])
def delete_brand(brand_id: str):
    path = BRANDS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Brand not found")
    path.unlink()
    return {"deleted": brand_id}


@app.post("/api/brands", dependencies=[Depends(api_auth)])
async def save_brand(request: Request):
    data = await request.json()
    brand_id = (data.get("brand_id") or "").strip()
    if not brand_id:
        raise HTTPException(status_code=400, detail="brand_id is required")
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    path = BRANDS_DIR / f"{brand_id}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    return {"saved": str(path)}


@app.get("/api/brands/{brand_id}/topics", dependencies=[Depends(api_auth)])
def get_topics(brand_id: str):
    from content_factory.topic_generator import load_topics
    data = load_topics(brand_id)
    if not data:
        raise HTTPException(status_code=404, detail="No topics found")
    return data


@app.post("/api/brands/{brand_id}/topics/generate", dependencies=[Depends(api_auth)])
def generate_topics_endpoint(brand_id: str):
    from content_factory.topic_generator import generate_topics, save_topics
    path = BRANDS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Brand not found")
    with open(path, encoding="utf-8") as f:
        brand = yaml.safe_load(f) or {}
    titles = generate_topics(brand)
    return save_topics(brand_id, titles, status="pending_approval")


@app.post("/api/brands/{brand_id}/generate", dependencies=[Depends(api_auth)])
def generate_content(brand_id: str, slot_type: str = "long_blog"):
    from content_factory.content_runner import run_for_brand
    result = run_for_brand(brand_id=brand_id, slot_type=slot_type)
    return result


@app.post("/api/brands/{brand_id}/topics/approve", dependencies=[Depends(api_auth)])
async def approve_topics_endpoint(brand_id: str, request: Request):
    from content_factory.topic_generator import save_topics
    body = await request.json()
    titles = body.get("titles", [])
    if not titles:
        raise HTTPException(status_code=400, detail="titles required")
    return save_topics(brand_id, titles, status="approved")


@app.get("/api/brands/{brand_id}/generated", dependencies=[Depends(api_auth)])
def list_generated(brand_id: str):
    d = GENERATED_DIR / brand_id
    if not d.exists():
        return []
    items = []
    for p in sorted(d.glob("*.yaml"), reverse=True):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        items.append({
            "run_id": p.stem,
            "topic": data.get("topic", ""),
            "slot_type": data.get("slot_type", "long_blog"),
            "generated_at": data.get("generated_at", ""),
            "status": data.get("status", "pending_review"),
        })
    return items


@app.get("/api/brands/{brand_id}/generated/{run_id}", dependencies=[Depends(api_auth)])
def get_generated(brand_id: str, run_id: str):
    path = GENERATED_DIR / brand_id / f"{run_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated content not found")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@app.post("/api/brands/{brand_id}/generated/{run_id}/approve", dependencies=[Depends(api_auth)])
def approve_generated(brand_id: str, run_id: str):
    path = GENERATED_DIR / brand_id / f"{run_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated content not found")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    brand_path = BRANDS_DIR / f"{brand_id}.yaml"
    brand = yaml.safe_load(brand_path.read_text(encoding="utf-8")) or {}

    client_email = brand.get("client_email", "")
    client_name = brand.get("client_name") or brand_id
    if not client_email:
        raise HTTPException(status_code=400, detail="client_email not set on brand profile")

    from content_factory.emailer import send_delivery_email
    email_id = send_delivery_email(
        client_name=client_name, client_email=client_email,
        topic_title=data.get("topic", ""), content_markdown=data.get("content", ""),
        slot_type=data.get("slot_type", "long_blog"),
    )

    data["status"] = "approved"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    topics_path = TOPICS_DIR / f"{brand_id}.yaml"
    if topics_path.exists():
        td = yaml.safe_load(topics_path.read_text(encoding="utf-8")) or {}
        for t in td.get("topics", []):
            if t.get("title") == data.get("topic"):
                t["status"] = "sent"; break
        with open(topics_path, "w", encoding="utf-8") as f:
            yaml.dump(td, f, allow_unicode=True, sort_keys=False)

    return {"approved": True, "email_id": email_id}


@app.post("/api/brands/{brand_id}/generated/{run_id}/reject", dependencies=[Depends(api_auth)])
async def reject_generated(brand_id: str, run_id: str, request: Request):
    path = GENERATED_DIR / brand_id / f"{run_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated content not found")

    body = await request.json()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["status"] = "rejected"
    data["rejection_note"] = body.get("note", "")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    topics_path = TOPICS_DIR / f"{brand_id}.yaml"
    if topics_path.exists():
        td = yaml.safe_load(topics_path.read_text(encoding="utf-8")) or {}
        for t in td.get("topics", []):
            if t.get("title") == data.get("topic"):
                t["status"] = "pending"; break
        with open(topics_path, "w", encoding="utf-8") as f:
            yaml.dump(td, f, allow_unicode=True, sort_keys=False)

    return {"rejected": True}


# ── Status endpoint ───────────────────────────────────────────────────────────
@app.get("/api/status", dependencies=[Depends(api_auth)])
def get_status():
    result = {}

    if not BRANDS_DIR.exists():
        return result

    for brand_path in BRANDS_DIR.glob("*.yaml"):
        brand_id = brand_path.stem
        try:
            brand = yaml.safe_load(brand_path.read_text(encoding="utf-8")) or {}
        except Exception:
            brand = {}

        client_name = brand.get("client_name", brand_id)

        # Topics status
        topics_path = TOPICS_DIR / f"{brand_id}.yaml"
        topics_status = "none"
        topics_remaining = 0
        if topics_path.exists():
            try:
                td = yaml.safe_load(topics_path.read_text(encoding="utf-8")) or {}
                raw_status = td.get("status", "")
                if raw_status == "approved":
                    topics_status = "approved"
                else:
                    topics_status = "pending_approval"
                topics = td.get("topics", [])
                topics_remaining = sum(
                    1 for t in topics
                    if t.get("status") not in ("generated", "sent")
                )
            except Exception:
                pass

        # Pending review count
        pending_review_count = 0
        gen_dir = GENERATED_DIR / brand_id
        if gen_dir.exists():
            for gen_path in gen_dir.glob("*.yaml"):
                try:
                    gd = yaml.safe_load(gen_path.read_text(encoding="utf-8")) or {}
                    if gd.get("status") == "pending_review":
                        pending_review_count += 1
                except Exception:
                    pass

        result[brand_id] = {
            "client_name": client_name,
            "topics_status": topics_status,
            "pending_review_count": pending_review_count,
            "topics_remaining": topics_remaining,
        }

    return result


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8502))
    host = "0.0.0.0" if os.environ.get("PORT") else "localhost"
    uvicorn.run("onboarding_app:app", host=host, port=port, reload=not os.environ.get("PORT"))
