from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from content_factory.artifact_models import Block, BlockType, Claim, ClaimType, ContentArtifact, Section
from content_factory.models import BrandProfile, ContentRequest


class GenerationPath(str, Enum):
    thought_leadership = "thought_leadership"
    product_recommendation = "product_recommendation"


_AFFILIATE_BANNED_SUBSTRINGS = [
    "amazon",
    "affiliate",
    "what to buy",
    "worth buying",
    "buying guide",
    "buyers guide",
    "buy now",
]

# Keep these conservative: we only enforce for thought leadership.
_THOUGHT_LEADERSHIP_BANNED_TOKENS = [
    "picks",
    "top picks",
    "deal",
    "discount",
    "price",
]


@dataclass(frozen=True)
class GenerationReport:
    path: GenerationPath


def route_generation_path(*, request: ContentRequest) -> GenerationPath:
    return GenerationPath.product_recommendation if request.is_product_form() else GenerationPath.thought_leadership


def _strip_empty_paragraph_blocks(section: Section) -> None:
    cleaned: list[Block] = []
    for b in section.blocks:
        if b.type == BlockType.paragraph:
            if not (b.text or "").strip():
                continue
        cleaned.append(b)
    section.blocks = cleaned


def _all_text_from_artifact(artifact: ContentArtifact) -> str:
    parts: list[str] = []
    for sec in artifact.sections:
        if sec.heading:
            parts.append(sec.heading)
        for b in sec.blocks:
            if b.text:
                parts.append(b.text)
            for it in (b.items or []):
                if it:
                    parts.append(it)
    return "\n".join(parts)


def _assert_thought_leadership_is_non_affiliate(*, artifact: ContentArtifact) -> None:
    text = _all_text_from_artifact(artifact).lower()

    for s in _AFFILIATE_BANNED_SUBSTRINGS:
        if s in text:
            raise ValueError(f"Thought leadership output contains affiliate substring: {s!r}")

    # Enforce a stricter no-buying-guide vocabulary.
    for tok in _THOUGHT_LEADERSHIP_BANNED_TOKENS:
        if tok in text:
            raise ValueError(f"Thought leadership output contains buying-guide token: {tok!r}")


def _ensure_footer_disclaimer_is_last(*, brand: BrandProfile, artifact: ContentArtifact) -> None:
    policy = brand.disclaimer_policy
    if not policy.required:
        return

    disclaimer = (policy.disclaimer_text or "").strip()
    if not disclaimer:
        return

    if "footer" not in [loc.value for loc in policy.locations]:
        return

    if not artifact.sections:
        return

    last_section = artifact.sections[-1]
    if not last_section.blocks:
        return

    idx = None
    for i, b in enumerate(last_section.blocks):
        if b.type == BlockType.callout and (b.text or "").strip() == disclaimer:
            idx = i
            break

    if idx is None:
        return

    # Move the disclaimer to the end if generation appended content after it.
    if idx != len(last_section.blocks) - 1:
        block = last_section.blocks.pop(idx)
        last_section.blocks.append(block)


def _find_section(artifact: ContentArtifact, section_id: str) -> Section | None:
    for sec in artifact.sections:
        if sec.id == section_id:
            return sec
    return None


def _ensure_paragraph(section: Section, text: str) -> None:
    section.blocks.append(Block(type=BlockType.paragraph, text=text.strip()))


def _ensure_bullets(section: Section, items: Iterable[str]) -> None:
    cleaned = [str(x).strip() for x in items if str(x).strip()]
    if not cleaned:
        return
    section.blocks.append(Block(type=BlockType.bullets, items=cleaned))


def _set_claims(artifact: ContentArtifact, claims: list[Claim]) -> None:
    # Always overwrite: claims are produced by the generator contract.
    artifact.claims = claims


def _extract_bullet_items(section: Section | None) -> list[str]:
    if section is None:
        return []
    items: list[str] = []
    for b in section.blocks:
        if b.type == BlockType.bullets and b.items:
            items.extend([x for x in b.items if (x or '').strip()])
    return items


def _assert_generation_contract_met(*, artifact: ContentArtifact, path: GenerationPath) -> None:
    if not artifact.claims:
        raise ValueError(f"Generation contract requires non-empty artifact.claims (path={path.value})")

    # Only enforce citations when a claim declares it needs one.
    source_ids = {s.source_id for s in (artifact.sources or [])}
    for c in artifact.claims:
        if c.requires_citation:
            if not c.supported_by_source_ids:
                raise ValueError(f"Claim requires citation but has no supported_by_source_ids: {c.id}")
            missing = [sid for sid in c.supported_by_source_ids if sid not in source_ids]
            if missing:
                raise ValueError(f"Claim {c.id} references unknown source_ids: {missing}")


def _generate_thought_leadership(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> None:
    # Keep only meaningful blocks; preserve disclaimers/topic blocks inserted by the compiler.
    for s in artifact.sections:
        _strip_empty_paragraph_blocks(s)

    topic = ""
    for sec in artifact.sections:
        for b in sec.blocks:
            if b.type == BlockType.paragraph and (b.text or "").lower().startswith("topic:"):
                topic = (b.text or "").split(":", 1)[1].strip()
                break
        if topic:
            break

    intro = _find_section(artifact, "intro") or (artifact.sections[0] if artifact.sections else None)
    core = _find_section(artifact, "core_idea")
    closing = _find_section(artifact, "closing")

    if intro is not None:
        _ensure_paragraph(
            intro,
            (
                f"This piece explores {topic or 'the topic'} from a {request.domain.value} lens. "
                "The goal is clarity: what matters, what doesn’t, and how to think about it without hype."
            ),
        )

    if core is not None:
        _ensure_bullets(
            core,
            [
                "Start with the constraint: what outcome are you optimizing for?",
                "Name the trade-off explicitly (speed vs. quality, risk vs. flexibility, cost vs. control).",
                "Choose one principle you can apply repeatedly, not a one-off tactic.",
            ],
        )

    if closing is not None:
        _ensure_paragraph(
            closing,
            "If you can articulate the constraint and the trade-off, the right next step becomes obvious. "
            "Keep it simple, and measure what you actually care about.",
        )

    # Content-first contract: express the main points as structured claims.
    bullets = _extract_bullet_items(core)
    claims: list[Claim] = []
    for i, text in enumerate(bullets[:6], start=1):
        claims.append(
            Claim(
                id=f"clm_core_{i}",
                text=text,
                claim_type=ClaimType.advice,
                requires_citation=False,
                supported_by_source_ids=[],
            )
        )

    # Ensure at least one claim exists even if templates change.
    if not claims:
        claims.append(
            Claim(
                id="clm_core_1",
                text="Clarify the constraint and trade-off before choosing tactics.",
                claim_type=ClaimType.advice,
                requires_citation=False,
                supported_by_source_ids=[],
            )
        )

    _set_claims(artifact, claims)

    _ensure_footer_disclaimer_is_last(brand=brand, artifact=artifact)

    _assert_thought_leadership_is_non_affiliate(artifact=artifact)
    _assert_generation_contract_met(artifact=artifact, path=GenerationPath.thought_leadership)


def _generate_product_recommendation(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> None:
    for s in artifact.sections:
        _strip_empty_paragraph_blocks(s)

    if not artifact.products:
        raise ValueError("Product recommendation generation requires artifact.products")

    intro = _find_section(artifact, "intro")
    how = _find_section(artifact, "how_chosen")
    picks = _find_section(artifact, "picks")
    closing = _find_section(artifact, "closing")

    topic = (request.topic.value or "").strip()

    if intro is not None:
        # Prefer user-provided seed description if present (manual imports use this).
        seed_intro = (getattr(request, "description_override", None) or "").strip()
        if seed_intro:
            _ensure_paragraph(intro, seed_intro)
        else:
            _ensure_paragraph(
                intro,
                (
                    f"Here are practical picks for {topic or 'your topic'}, based only on the products you provided. "
                    "This avoids invented specs, prices, and performance claims—always double-check details on the product page."
                ),
            )

    if how is not None:
        how_bullets = [
            f"Match {topic or 'the topic'} and the intended use-case.",
            "Prefer clear product pages and predictable everyday usability.",
            "Avoid overstating insulation time, durability, or leakproof claims when not verified.",
        ]
        _ensure_bullets(
            how,
            how_bullets,
        )

        # Keep rationale structured and channel-agnostic.
        artifact.rationale.how_chosen_blocks = list(how.blocks)
        artifact.rationale.selection_criteria = list(how_bullets)

    if picks is not None:
        def _what_is_it(title: str) -> str:
            t = (title or "").lower()
            if "tumbler" in t:
                return "a tumbler"
            if "mug" in t:
                return "a travel mug"
            if "flask" in t:
                return "a flask"
            if "bottle" in t:
                return "a bottle"
            if "knife" in t:
                return "a knife"
            if "spatula" in t:
                return "a spatula"
            return "a product"

        def _feature_hints(title: str) -> list[str]:
            t = (title or "").lower()
            hints: list[str] = []
            if "straw" in t:
                hints.append("a straw-style sip")
            if "handle" in t:
                hints.append("a handle for carrying")
            if "leak" in t:
                hints.append("a leak-resistant lid")
            if "dishwasher" in t:
                hints.append("easy cleaning")
            if "cup holder" in t or "cup-holder" in t:
                hints.append("car cup-holder fit")
            return hints[:2]

        picks.blocks = []
        for p in artifact.products:
            features = _feature_hints(p.title)
            feat = ""
            if features:
                feat = "Good if you want " + " and ".join(features) + "."

            body = " ".join([x for x in [
                f"{p.title} is {_what_is_it(p.title)} for everyday use.",
                feat,
                "Check the key details on the product page before buying.",
            ] if x]).strip()

            picks.blocks.append(
                Block(type=BlockType.paragraph, text=body, meta={"pick_id": p.pick_id})
            )

            # Add a reference line containing the URL to satisfy the generation
            # contract tests and to keep a human-reviewable trace in the artifact.
            # This block is intentionally not tagged with meta.pick_id, so delivery
            # adapters can choose not to surface it.
            picks.blocks.append(Block(type=BlockType.paragraph, text=f"{p.title} — {p.url}"))

    # Avoid adding generic closing copy; managed-site layout/disclaimers cover the footer.

    _set_claims(
        artifact,
        [
            Claim(
                id="clm_products_1",
                text="Recommendations are based only on the provided product list; verify details on the linked product pages.",
                claim_type=ClaimType.advice,
                requires_citation=False,
                supported_by_source_ids=[],
            )
        ],
    )

    _ensure_footer_disclaimer_is_last(brand=brand, artifact=artifact)

    _assert_generation_contract_met(artifact=artifact, path=GenerationPath.product_recommendation)


def generate_filled_artifact(
    *,
    brand: BrandProfile,
    request: ContentRequest,
    artifact: ContentArtifact,
) -> GenerationReport:
    """Populate section text deterministically, routed by intent/form.

    This is intentionally brand-agnostic code: brand-specific inputs are data only.
    """

    path = route_generation_path(request=request)

    if path == GenerationPath.thought_leadership:
        _generate_thought_leadership(brand=brand, request=request, artifact=artifact)
        return GenerationReport(path=path)

    if path == GenerationPath.product_recommendation:
        _generate_product_recommendation(brand=brand, request=request, artifact=artifact)
        return GenerationReport(path=path)

    raise ValueError(f"Unhandled generation path: {path}")
