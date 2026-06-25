"""
LLM-based article writer.

Takes a brand profile + topic and produces a full markdown article
using the voice, tone, audience, and persona captured at onboarding.
"""
from __future__ import annotations

from integrations.openai_adapters import make_llm

PERSONA_DESCRIPTIONS = {
    "calm_authoritative": "calm, measured, and authoritative — grounded in evidence, never hyperbolic",
    "warm_reflective": "warm and reflective, quietly confident — like a trusted mentor sharing hard-won insight",
    "direct_insight_dense": "direct and insight-dense — short sentences, no filler, every line earns its place",
    "practical_expert": "conversational but expert — approachable language, real-world grounding, never academic",
    "minimalist_executive": "minimal and executive — crisp, declarative, respects the reader's intelligence and time",
}

AUDIENCE_DESCRIPTIONS = {
    "c_suite_senior_leaders": "C-suite executives and senior leaders",
    "entrepreneurs_founders": "entrepreneurs and founders building their own ventures",
    "coaches_consultants_speakers": "coaches, consultants, and professional speakers",
    "everyday_consumers_shoppers": "everyday consumers looking for practical recommendations",
    "hobbyists_enthusiasts": "hobbyists and enthusiasts who are passionate about the subject",
    "travelers_experience_seekers": "travelers and people seeking meaningful experiences",
    "professionals_specific_field": "professionals in a specific field",
}

ROLE_DESCRIPTIONS = {
    "mentor_coach": "a mentor and coach",
    "product_ranker": "a product expert known for ranking and comparing options",
    "product_guide": "a deep expert on a specific product or niche",
    "reviewer": "a trusted reviewer who shares honest, opinionated evaluations",
    "travel_guide": "a travel guide and storyteller",
}


def _build_voice_block(brand: dict) -> str:
    domains = brand.get("domains_supported") or []
    persona_cfg = (brand.get("persona_by_domain") or {}).get(domains[0] if domains else "", {})

    persona_key = persona_cfg.get("primary_persona", "practical_expert")
    persona_desc = PERSONA_DESCRIPTIONS.get(persona_key, persona_key.replace("_", " "))

    narration = persona_cfg.get("narration_mode", "third_person_only")
    presence = persona_cfg.get("personal_presence", "none")
    science = persona_cfg.get("science_explicitness", "implied")

    aud_key = (brand.get("audience") or {}).get("primary_audience", "")
    aud_ctx = (brand.get("audience") or {}).get("audience_context", "")
    audience = AUDIENCE_DESCRIPTIONS.get(aud_key, aud_key.replace("_", " "))
    if aud_ctx:
        audience += f" — specifically {aud_ctx}"

    role_key = brand.get("brand_archetype", "mentor_coach")
    role = ROLE_DESCRIPTIONS.get(role_key, role_key.replace("_", " "))

    lines = [
        f"You are writing as {role}.",
        f"Audience: {audience}.",
        f"Voice: {persona_desc}.",
    ]

    if narration in ("first_person_allowed", "first_person_preferred"):
        lines.append("Use first-person voice where it feels natural and adds credibility.")
    else:
        lines.append("Write in third-person — no 'I' statements.")

    if presence == "frequent_personal_anecdotes":
        lines.append("Include personal observations or anecdotes to ground the ideas.")
    elif presence == "occasional_personal_anecdotes":
        lines.append("An occasional personal observation is fine, but insight should lead.")
    else:
        lines.append("Keep it idea-led — no personal anecdotes.")

    if science == "explicit_often":
        lines.append("Reference research, neuroscience, or data explicitly and often.")
    elif science == "explicit_when_credibility_helpful":
        lines.append("Reference research or science when it adds credibility — not gratuitously.")
    else:
        lines.append("Keep science implied — don't cite studies or use academic language.")

    comm = (brand.get("commercial_policy") or {}).get("commercial_posture", "invisible")
    if comm == "invisible":
        lines.append("No commercial angle whatsoever — pure value.")
    elif comm == "soft_recommendation":
        lines.append("Authority comes from expertise, not selling. No CTAs.")
    elif comm in ("clear_recommendation", "explicit_cta"):
        cta = (brand.get("commercial_policy") or {}).get("cta_policy", "none")
        if cta == "gentle_cta_at_end":
            lines.append("End with a single, low-pressure invitation to connect or learn more.")
        elif cta == "clear_invitation":
            lines.append("End with a clear, direct invitation to work together.")

    return "\n".join(lines)


def _samples_block(brand: dict) -> str:
    samples = (brand.get("writing_samples") or "").strip()
    if not samples:
        return ""
    return f"\n\nExamples of their actual writing (match this voice closely):\n\"\"\"\n{samples[:3000]}\n\"\"\""


def write_long_blog(brand: dict, topic: str) -> str:
    """Generate a full blog article (~900-1200 words) as markdown."""
    about = ((brand.get("topic_policy") or {}).get("allowlist") or [""])[0]
    voice_block = _build_voice_block(brand)
    client_name = brand.get("client_name") or brand.get("brand_id", "")
    samples_block = _samples_block(brand)

    system = f"""You are a world-class ghostwriter specialising in thought-leadership content.
You write in the exact voice of the person you represent — not generically.
Return a JSON object with two keys:
  "title": the final article title (may refine the prompt title)
  "body": the full article in markdown (use ## for section headings, no H1)"""

    user = f"""{voice_block}{samples_block}

The client is: {client_name}
What they write about: {about}

Write a full thought-leadership article on this topic:
"{topic}"

Requirements:
- Length: 900–1200 words
- Open with a compelling hook — a specific observation, provocative statement, or vivid scenario (not "In today's world…")
- Use 3–4 sections with ## headings that feel editorial, not generic (avoid "Introduction", "Conclusion")
- End with a strong closing paragraph that leaves the reader with one clear idea to sit with
- No bullet-point lists — flowing prose only
- No fluff, no corporate-speak, no filler transitions
- The insight should feel earned, not obvious"""

    llm = make_llm(brand)
    result = llm.complete_json(system=system, user=user)
    title = result.get("title", topic)
    body = result.get("body", "")
    return f"# {title}\n\n{body}"


def write_short_snippet(brand: dict, topic: str) -> str:
    """Generate a short-form post (~200-280 words) as markdown."""
    voice_block = _build_voice_block(brand)
    client_name = brand.get("client_name") or brand.get("brand_id", "")
    samples_block = _samples_block(brand)

    system = f"""You are a world-class ghostwriter specialising in short-form thought-leadership content.
Return a JSON object with two keys:
  "title": a short, punchy headline
  "body": the post body in markdown (no headings — just flowing paragraphs)"""

    user = f"""{voice_block}{samples_block}

The client is: {client_name}

Write a short-form post (~200-280 words) on this topic:
"{topic}"

Requirements:
- Open with a single strong sentence that makes the reader stop scrolling
- 2–3 tight paragraphs — no waffle
- Ends with one concrete thought, question, or observation
- No bullet points
- No hashtags
- Feels human, not AI-generated"""

    llm = make_llm(brand)
    result = llm.complete_json(system=system, user=user)
    title = result.get("title", topic)
    body = result.get("body", "")
    return f"# {title}\n\n{body}"


def write_article(brand: dict, topic: str, slot_type: str = "long_blog") -> str:
    if slot_type == "short_snippet":
        return write_short_snippet(brand, topic)
    return write_long_blog(brand, topic)
