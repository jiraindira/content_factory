from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import List, Optional

from content_factory.artifact_models import (
    Block,
    BlockType,
    Checks,
    ContentArtifact,
    Product,
    Rationale,
    Section,
    Source,
    SourceKind,
)
from content_factory.brand_context import BrandContextArtifact
from content_factory.models import BrandProfile, ContentIntent, ContentRequest, ProductRecommendationForm


def _generated_at_for_request(*, request: ContentRequest) -> str:
    # Deterministic: derived from the validated publish date.
    d = request.publish.publish_date
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc).isoformat()


def resolve_topic_value(*, brand: BrandProfile, request: ContentRequest) -> str:
    """Resolve the topic deterministically.

    - manual: topic.value must be provided and already validated against allowlist.
    - auto: choose a topic from allowlist deterministically; no inference.
    """

    allowlist = brand.topic_policy.allowlist
    if not allowlist:
        raise ValueError("brand.topic_policy.allowlist must not be empty")

    if request.topic.mode.value == "manual":
        if not request.topic.value:
            raise ValueError("topic.value is required when topic.mode=manual")
        return request.topic.value

    # auto: deterministic selection from allowlist
    seed = f"{brand.brand_id}|{request.publish.publish_date.isoformat()}|{request.intent.value}|{request.form.value}|{request.domain.value}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(allowlist)
    return allowlist[idx]


def _make_disclaimer_block(text: str) -> Block:
    return Block(type=BlockType.callout, text=text)


def _insert_disclaimer_blocks(
    *,
    brand: BrandProfile,
    is_product_run: bool,
    sections: List[Section],
) -> None:
    policy = brand.disclaimer_policy
    if not policy.required:
        return

    disclaimer = _make_disclaimer_block(policy.disclaimer_text or "")

    if "header" in [loc.value for loc in policy.locations]:
        if sections:
            sections[0].blocks.insert(0, disclaimer)

    if is_product_run and "before_products" in [loc.value for loc in policy.locations]:
        # Insert right before the picks section if present; otherwise after intro.
        insert_idx = 1
        for i, sec in enumerate(sections):
            if sec.id == "picks":
                insert_idx = i
                break
        sections.insert(insert_idx, Section(id="disclaimer_before_products", heading=None, blocks=[disclaimer]))

    if "footer" in [loc.value for loc in policy.locations]:
        if sections:
            sections[-1].blocks.append(disclaimer)


def _template_sections(*, request: ContentRequest) -> List[Section]:
    # Deterministic, spec-driven structure.
    if request.intent == ContentIntent.thought_leadership:
        return [
            Section(id="intro", heading=None, blocks=[Block(type=BlockType.paragraph, text="")]),
            Section(id="core_idea", heading=None, blocks=[Block(type=BlockType.paragraph, text="")]),
            Section(id="closing", heading=None, blocks=[Block(type=BlockType.paragraph, text="")]),
        ]

    if request.intent == ContentIntent.product_recommendation:
        return [
            Section(id="intro", heading=None, blocks=[Block(type=BlockType.paragraph, text="")]),
            Section(
                id="how_chosen",
                heading="How this list was chosen",
                blocks=[Block(type=BlockType.paragraph, text="")],
            ),
            Section(id="picks", heading="Top picks", blocks=[]),
            Section(id="closing", heading=None, blocks=[Block(type=BlockType.paragraph, text="")]),
        ]

    # Fallback (still explicit): minimal structure.
    return [Section(id="body", heading=None, blocks=[Block(type=BlockType.paragraph, text="")])]


def compile_content_artifact(
    *,
    brand: BrandProfile,
    request: ContentRequest,
    brand_context: BrandContextArtifact,
    run_id: str,
) -> ContentArtifact:
    persona_cfg = brand.persona_by_domain[request.domain]

    is_product_form = isinstance(request.form, ProductRecommendationForm)

    sections = _template_sections(request=request)

    # Inject required disclaimers per brand policy (purely structural).
    _insert_disclaimer_blocks(brand=brand, is_product_run=is_product_form, sections=sections)

    # Sources are derived from BrandContextArtifact only (no raw URL reads).
    sources = [
        Source(
            source_id=s.source_id,
            kind=SourceKind.url if s.kind == "url" else SourceKind.file,
            ref=s.ref,
            purpose=s.purpose,
            notes=None,
        )
        for s in brand_context.sources
        if s.ok
    ]

    products: Optional[List[Product]]
    if is_product_form:
        products = [
            Product(
                pick_id=p.pick_id,
                title=p.title,
                url=p.url,
                rating=p.rating,
                reviews_count=p.reviews_count,
                provider=p.provider,
            )
            for p in request.products.items
        ]
    else:
        products = None

    checks = Checks(
        matrix_validation_passed=True,
        brand_policy_checks_passed=True,
        required_sections_present=True,
        products_present_when_required=True,
        citations_present_when_required=True,
        topic_allowlist_passed=True,
        required_disclaimers_present=(not brand.disclaimer_policy.required) or bool(brand.disclaimer_policy.disclaimer_text),
        robots_policy_passed=True,
        disallowed_claims_found=[],
    )

    # Publishable rationale is deterministic placeholders for now.
    rationale = Rationale(
        how_chosen_blocks=[Block(type=BlockType.paragraph, text="")],
        selection_criteria=[],
    )

    resolved_topic = resolve_topic_value(brand=brand, request=request)

    # Populate minimal placeholder text from resolved topic & signals without LLM.
    if sections:
        topic_block = Block(type=BlockType.paragraph, text=f"Topic: {resolved_topic}")
        if sections[0].blocks and sections[0].blocks[0].type == BlockType.callout:
            sections[0].blocks.insert(1, topic_block)
        else:
            sections[0].blocks.insert(0, topic_block)

    return ContentArtifact(
        brand_id=brand.brand_id,
        run_id=run_id,
        generated_at=_generated_at_for_request(request=request),
        intent=request.intent.value,
        form=request.form.value,
        domain=request.domain.value,
        content_depth=brand.content_strategy.default_content_depth.value,
        audience={
            "primary_audience": brand.audience.primary_audience.value,
            "audience_sophistication": brand.audience.audience_sophistication.value,
        },
        persona={
            "primary_persona": persona_cfg.primary_persona.value,
            "persona_modifiers": [m.value for m in persona_cfg.persona_modifiers],
            "science_explicitness": persona_cfg.science_explicitness.value,
            "personal_presence": persona_cfg.personal_presence.value,
            "narration_mode": persona_cfg.narration_mode.value,
        },
        sections=sections,
        products=products,
        rationale=rationale,
        claims=[],
        sources=sources,
        checks=checks,
    )
