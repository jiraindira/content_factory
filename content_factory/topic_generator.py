"""
Topic generator — produces N article topic titles for a brand profile.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from integrations.openai_adapters import make_llm

TOPICS_DIR = Path(__file__).parent / "topics"

ROLE_LABELS = {
    "mentor_coach": "Mentor / Coach",
    "product_ranker": "Product Ranker",
    "product_guide": "Product Guide",
    "reviewer": "Reviewer",
    "travel_guide": "Travel Guide",
}

PERSONA_LABELS = {
    "calm_authoritative": "calm, authoritative, science-led",
    "warm_reflective": "warm, reflective, quietly confident",
    "direct_insight_dense": "direct, sharp, insight-dense",
    "practical_expert": "conversational but expert",
    "minimalist_executive": "executive and minimal",
}

AUDIENCE_LABELS = {
    "c_suite_senior_leaders": "C-suite and senior leaders",
    "entrepreneurs_founders": "entrepreneurs and founders",
    "coaches_consultants_speakers": "coaches, consultants and speakers",
    "everyday_consumers_shoppers": "everyday consumers and shoppers",
    "hobbyists_enthusiasts": "hobbyists and enthusiasts",
    "travelers_experience_seekers": "travelers and experience seekers",
    "professionals_specific_field": "professionals in a specific field",
}


def _build_prompt(brand: dict, n: int) -> str:
    role = ROLE_LABELS.get(brand.get("brand_archetype", ""), brand.get("brand_archetype", ""))
    aud_key = (brand.get("audience") or {}).get("primary_audience", "")
    audience = AUDIENCE_LABELS.get(aud_key, aud_key.replace("_", " "))
    aud_ctx = (brand.get("audience") or {}).get("audience_context", "")

    about_list = (brand.get("topic_policy") or {}).get("allowlist") or []
    about = about_list[0] if about_list else ""

    domains = brand.get("domains_supported") or []
    persona_cfg = (brand.get("persona_by_domain") or {}).get(domains[0] if domains else "", {})
    persona = PERSONA_LABELS.get(persona_cfg.get("primary_persona", ""), "")

    audience_line = audience
    if aud_ctx:
        audience_line += f" — specifically {aud_ctx}"

    return f"""You are a senior content strategist planning a {n}-article content series.

Client profile:
- Creator role: {role}
- Primary audience: {audience_line}
- What they write about: {about}
- Writing tone: {persona}

Generate exactly {n} article topic titles for this client.

Each title must be:
- Specific and compelling, not generic
- Directly relevant to the audience's real concerns and daily challenges
- Varied in angle across the series — include a mix of: practical how-to, reframing assumptions, insight-led pieces, myth-busting, and challenging conventional wisdom
- Written as a polished, publish-ready article title

Return ONLY a JSON object with a single key "topics" whose value is an array of exactly {n} strings.
No explanation, no numbering, no extra text."""


_TOPICS_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["topics"],
    "additionalProperties": False,
}


def generate_topics(brand: dict) -> list[str]:
    n = int(brand.get("package_size") or 8)
    llm = make_llm(brand)
    result = llm.complete_json(
        system="You are a senior content strategist. Return only valid JSON.",
        user=_build_prompt(brand, n),
        schema=_TOPICS_SCHEMA,
        reference_document=(brand.get("reference_text") or None),
    )
    topics = result.get("topics", [])
    if not isinstance(topics, list):
        raise ValueError(f"Unexpected response shape: {result}")
    return [str(t).strip() for t in topics[:n]]


def load_topics(brand_id: str) -> dict | None:
    path = TOPICS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f) or None


def save_topics(brand_id: str, titles: list[str], status: str = "pending_approval") -> dict:
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_topics(brand_id) or {}
    data = {
        "brand_id": brand_id,
        "status": status,
        "generated_at": existing.get("generated_at") or str(date.today()),
        "approved_at": existing.get("approved_at") if status == "approved" else None,
        "topics": [
            {"id": i + 1, "title": t}
            for i, t in enumerate(titles)
        ],
    }
    if status == "approved":
        data["approved_at"] = str(date.today())

    path = TOPICS_DIR / f"{brand_id}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    return data
