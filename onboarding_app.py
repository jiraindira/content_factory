"""
Content Factory — Client Onboarding API
Run with: poetry run python onboarding_app.py
Opens automatically at http://localhost:8502
"""

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
    with open(path) as f:
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
    with open(path, "w") as f:
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
    with open(path) as f:
        brand = yaml.safe_load(f) or {}
    titles = generate_topics(brand)
    return save_topics(brand_id, titles, status="pending_approval")


@app.post("/api/brands/{brand_id}/topics/approve")
async def approve_topics_endpoint(brand_id: str, request: Request):
    from content_factory.topic_generator import save_topics
    body = await request.json()
    titles = body.get("titles", [])
    if not titles:
        raise HTTPException(status_code=400, detail="titles required")
    return save_topics(brand_id, titles, status="approved")


if __name__ == "__main__":
    uvicorn.run("onboarding_app:app", host="localhost", port=8502, reload=True)
