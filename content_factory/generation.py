from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from content_factory.artifact_models import Block, BlockType, ContentArtifact, Section
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

    _assert_thought_leadership_is_non_affiliate(artifact=artifact)


def _generate_product_recommendation(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> None:
    for s in artifact.sections:
        _strip_empty_paragraph_blocks(s)

    if not artifact.products:
        raise ValueError("Product recommendation generation requires artifact.products")

    intro = _find_section(artifact, "intro")
    how = _find_section(artifact, "how_chosen")
    picks = _find_section(artifact, "picks")
    closing = _find_section(artifact, "closing")

    if intro is not None:
        _ensure_paragraph(
            intro,
            "This list is based on your provided products. It avoids invented specs, prices, and performance claims.",
        )

    if how is not None:
        _ensure_bullets(
            how,
            [
                "Match the topic and intended use-case.",
                "Prefer reputable sellers and clear product pages.",
                "Avoid overstating performance when details are unknown.",
            ],
        )

    if picks is not None:
        _ensure_bullets(
            picks,
            [f"{p.title} — {p.url}" for p in artifact.products],
        )

    if closing is not None:
        _ensure_paragraph(
            closing,
            "If you’re unsure, start with the option that best matches your constraints, then adjust after real-world use.",
        )


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
