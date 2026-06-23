"""
Content runner — generates an article from an approved topic and emails it for review.

Flow:
  1. Load brand profile + next pending topic
  2. Build a ContentRequest YAML
  3. Run the generation pipeline
  4. Render to markdown
  5. Save to content_factory/generated/<brand_id>/
  6. Email to operator for review
  7. Mark topic as generated/pending_review
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[1]
BRANDS_DIR = REPO_ROOT / "content_factory" / "brands"
TOPICS_DIR = REPO_ROOT / "content_factory" / "topics"
GENERATED_DIR = REPO_ROOT / "content_factory" / "generated"
REQUESTS_DIR = REPO_ROOT / "content_factory" / "requests"


def _slug(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60].strip("-")


def _next_pending_topic(brand_id: str) -> dict | None:
    path = TOPICS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text()) or {}
    if data.get("status") != "approved":
        return None
    for t in data.get("topics", []):
        if t.get("status") not in ("generated", "sent"):
            return t
    return None


def _mark_topic_generated(brand_id: str, topic_id: int) -> None:
    path = TOPICS_DIR / f"{brand_id}.yaml"
    data = yaml.safe_load(path.read_text()) or {}
    for t in data.get("topics", []):
        if t["id"] == topic_id:
            t["status"] = "generated"
            break
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


def _build_request_yaml(brand: dict, topic_title: str, slot_type: str) -> Path:
    """Write a ContentRequest YAML and return its path."""
    brand_id = brand["brand_id"]
    domain = brand.get("domain_primary", (brand.get("domains_supported") or ["leadership"])[0])

    # Pick intent and form from brand strategy
    strategy = brand.get("content_strategy", {})
    intents = strategy.get("allowed_intents", ["thought_leadership"])
    intent = intents[0]

    tl_forms = strategy.get("allowed_thought_leadership_forms", [])
    pr_forms = strategy.get("allowed_product_recommendation_forms", [])
    form = (tl_forms or pr_forms or ["core_insight_essay"])[0]

    # Delivery target from brand policy
    delivery = brand.get("delivery_policy", {})
    channels = delivery.get("delivery_channels", ["blog_article"])
    destinations = delivery.get("delivery_destinations", ["hosted_by_us"])

    # For short snippets prefer social channel if available
    if slot_type == "short_snippet":
        channel = next((c for c in channels if "social" in c), channels[0])
        destination = next((d for d in destinations if d not in ("hosted_by_us",)), destinations[0])
    else:
        channel = next((c for c in channels if c == "blog_article"), channels[0])
        destination = destinations[0]

    request = {
        "brand_id": brand_id,
        "publish": {"publish_date": str(date.today())},
        "intent": intent,
        "form": form,
        "domain": domain,
        "topic": {"mode": "manual", "value": topic_title},
        "delivery_target": {"destination": destination, "channel": channel},
        "products": {"mode": "none", "items": []},
    }

    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(topic_title)
    path = REQUESTS_DIR / f"{brand_id}_{date.today()}_{slug}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(request, f, allow_unicode=True, sort_keys=False)
    return path


def _save_generated(brand_id: str, topic_title: str, markdown: str, slot_type: str) -> Path:
    out_dir = GENERATED_DIR / brand_id
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(topic_title)
    path = out_dir / f"{date.today()}_{slug}.md"
    data = {
        "brand_id": brand_id,
        "topic": topic_title,
        "slot_type": slot_type,
        "generated_at": str(date.today()),
        "status": "pending_review",
        "content": markdown,
    }
    # Save as YAML with content embedded so the UI can load it
    yaml_path = out_dir / f"{date.today()}_{slug}.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    # Also save plain markdown for readability
    path.write_text(markdown, encoding="utf-8")
    return yaml_path


def run_for_brand(brand_id: str, slot_type: str = "long_blog") -> dict:
    """
    Generate content for the next pending topic for a brand.
    Returns a dict with keys: brand_id, topic, content_path, email_id
    """
    from content_factory.article_writer import write_article
    from content_factory.emailer import send_review_email

    brand_path = BRANDS_DIR / f"{brand_id}.yaml"
    if not brand_path.exists():
        raise FileNotFoundError(f"Brand not found: {brand_id}")

    brand_dict = yaml.safe_load(brand_path.read_text()) or {}
    topic = _next_pending_topic(brand_id)
    if not topic:
        return {"brand_id": brand_id, "status": "no_pending_topics"}

    topic_title = topic["title"]
    print(f"[{brand_id}] Generating: {topic_title}")

    # Generate article directly with LLM
    markdown = write_article(brand_dict, topic_title, slot_type)
    print(f"[{brand_id}] Article written ({len(markdown)} chars)")

    # Save locally
    content_path = _save_generated(brand_id, topic_title, markdown, slot_type)
    print(f"[{brand_id}] Saved: {content_path}")

    # Mark topic as generated
    _mark_topic_generated(brand_id, topic["id"])

    # Email to operator for review
    client_name = brand_dict.get("client_name") or brand_id
    email_id = send_review_email(
        client_name=client_name,
        client_brand_id=brand_id,
        topic_title=topic_title,
        content_markdown=markdown,
        slot_type=slot_type,
    )
    print(f"[{brand_id}] Review email sent: {email_id}")

    return {
        "brand_id": brand_id,
        "topic": topic_title,
        "content_path": str(content_path),
        "email_id": email_id,
        "status": "generated",
    }
