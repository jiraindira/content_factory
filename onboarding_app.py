"""
Content Factory — Client Onboarding API
Run with: poetry run python onboarding_app.py
Opens automatically at http://localhost:8502
"""

import os
from pathlib import Path

import uvicorn
import yaml
import sys
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

app = FastAPI()
BRANDS_DIR = Path(__file__).parent / "content_factory" / "brands"
HTML_FILE = Path(__file__).parent / "onboarding.html"


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(HTML_FILE)


@app.get("/api/brands")
def list_brands():
    if not BRANDS_DIR.exists():
        return []
    return sorted(p.stem for p in BRANDS_DIR.glob("*.yaml"))


@app.get("/api/brands/{brand_id}")
def get_brand(brand_id: str):
    path = BRANDS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Brand not found")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@app.delete("/api/brands/{brand_id}")
def delete_brand(brand_id: str):
    path = BRANDS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Brand not found")
    path.unlink()
    return {"deleted": brand_id}


@app.post("/api/brands")
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


@app.get("/api/brands/{brand_id}/topics")
def get_topics(brand_id: str):
    from content_factory.topic_generator import load_topics
    data = load_topics(brand_id)
    if not data:
        raise HTTPException(status_code=404, detail="No topics found")
    return data


@app.post("/api/brands/{brand_id}/topics/generate")
def generate_topics_endpoint(brand_id: str):
    from content_factory.topic_generator import generate_topics, save_topics
    path = BRANDS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Brand not found")
    with open(path, encoding="utf-8") as f:
        brand = yaml.safe_load(f) or {}
    titles = generate_topics(brand)
    return save_topics(brand_id, titles, status="pending_approval")


@app.post("/api/brands/{brand_id}/generate")
def generate_content(brand_id: str, slot_type: str = "long_blog"):
    from content_factory.content_runner import run_for_brand
    result = run_for_brand(brand_id=brand_id, slot_type=slot_type)
    return result


@app.post("/api/brands/{brand_id}/topics/approve")
async def approve_topics_endpoint(brand_id: str, request: Request):
    from content_factory.topic_generator import save_topics
    body = await request.json()
    titles = body.get("titles", [])
    if not titles:
        raise HTTPException(status_code=400, detail="titles required")
    return save_topics(brand_id, titles, status="approved")


GENERATED_DIR = Path(__file__).parent / "content_factory" / "generated"
TOPICS_DIR = Path(__file__).parent / "content_factory" / "topics"


@app.get("/api/brands/{brand_id}/generated")
def list_generated(brand_id: str):
    d = GENERATED_DIR / brand_id
    if not d.exists():
        return []
    items = []
    for p in sorted(d.glob("*.yaml"), reverse=True):
        data = yaml.safe_load(p.read_text()) or {}
        items.append({
            "run_id": p.stem,
            "topic": data.get("topic", ""),
            "slot_type": data.get("slot_type", "long_blog"),
            "generated_at": data.get("generated_at", ""),
            "status": data.get("status", "pending_review"),
        })
    return items


@app.get("/api/brands/{brand_id}/generated/{run_id}")
def get_generated(brand_id: str, run_id: str):
    path = GENERATED_DIR / brand_id / f"{run_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated content not found")
    return yaml.safe_load(path.read_text()) or {}


@app.post("/api/brands/{brand_id}/generated/{run_id}/approve")
def approve_generated(brand_id: str, run_id: str):
    path = GENERATED_DIR / brand_id / f"{run_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated content not found")

    data = yaml.safe_load(path.read_text()) or {}
    brand_path = BRANDS_DIR / f"{brand_id}.yaml"
    brand = yaml.safe_load(brand_path.read_text()) or {}

    client_email = brand.get("client_email", "")
    client_name = brand.get("client_name") or brand_id

    if not client_email:
        raise HTTPException(status_code=400, detail="client_email not set on brand profile")

    from content_factory.emailer import send_delivery_email
    email_id = send_delivery_email(
        client_name=client_name,
        client_email=client_email,
        topic_title=data.get("topic", ""),
        content_markdown=data.get("content", ""),
        slot_type=data.get("slot_type", "long_blog"),
    )

    # Mark generated content as approved
    data["status"] = "approved"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    # Mark topic as sent
    topics_path = TOPICS_DIR / f"{brand_id}.yaml"
    if topics_path.exists():
        topics_data = yaml.safe_load(topics_path.read_text()) or {}
        for t in topics_data.get("topics", []):
            if t.get("title") == data.get("topic"):
                t["status"] = "sent"
                break
        with open(topics_path, "w", encoding="utf-8") as f:
            yaml.dump(topics_data, f, allow_unicode=True, sort_keys=False)

    return {"approved": True, "email_id": email_id}


@app.post("/api/brands/{brand_id}/generated/{run_id}/reject")
async def reject_generated(brand_id: str, run_id: str, request: Request):
    path = GENERATED_DIR / brand_id / f"{run_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Generated content not found")

    body = await request.json()
    note = body.get("note", "")

    data = yaml.safe_load(path.read_text()) or {}
    data["status"] = "rejected"
    data["rejection_note"] = note
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    # Put topic back to pending so it can be regenerated
    topics_path = TOPICS_DIR / f"{brand_id}.yaml"
    if topics_path.exists():
        topics_data = yaml.safe_load(topics_path.read_text()) or {}
        for t in topics_data.get("topics", []):
            if t.get("title") == data.get("topic"):
                t["status"] = "pending"
                break
        with open(topics_path, "w", encoding="utf-8") as f:
            yaml.dump(topics_data, f, allow_unicode=True, sort_keys=False)

    return {"rejected": True}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8502))
    host = "0.0.0.0" if os.environ.get("PORT") else "localhost"
    uvicorn.run("onboarding_app:app", host=host, port=port, reload=not os.environ.get("PORT"))
