from __future__ import annotations

from typing import Any

from content_factory.artifact_models import Block, BlockType, ContentArtifact, Section
from content_factory.models import BrandProfile, ContentRequest, ContentIntent


def _find_section(artifact: ContentArtifact, section_id: str) -> Section | None:
    for sec in artifact.sections:
        if sec.id == section_id:
            return sec
    return None


def _blocks_to_markdown(blocks: list[Block]) -> str:
    parts: list[str] = []
    for b in blocks or []:
        if b.type == BlockType.paragraph:
            t = (b.text or "").strip()
            if t:
                parts.append(t)
            continue

        if b.type == BlockType.bullets:
            items = [(x or "").strip() for x in (b.items or []) if (x or "").strip()]
            if items:
                parts.append("\n".join([f"- {it}" for it in items]))
            continue

        if b.type == BlockType.numbered:
            items = [(x or "").strip() for x in (b.items or []) if (x or "").strip()]
            if items:
                parts.append("\n".join([f"{i}. {it}" for i, it in enumerate(items, start=1)]))
            continue

        if b.type in (BlockType.callout, BlockType.quote):
            t = (b.text or "").strip()
            if t:
                parts.append(t)
            continue

        # divider or unknown: ignore

    return "\n\n".join([p for p in parts if p.strip()]).strip()


def _set_section_markdown(section: Section, md: str) -> None:
    section.blocks = [Block(type=BlockType.paragraph, text=(md or "").strip())]


def apply_copy_editor_to_artifact_if_applicable(
    *,
    brand: BrandProfile,
    request: ContentRequest,
    artifact: ContentArtifact,
) -> bool:
    """Body-only editorial pass for product recommendation artifacts.

    Returns True if edits were applied, False if skipped.
    """

    if request.intent != ContentIntent.product_recommendation:
        return False

    # Only apply when products exist; editor uses product titles to craft pick bodies.
    if not artifact.products:
        return False

    intro = _find_section(artifact, "intro")
    how = _find_section(artifact, "how_chosen")
    picks = _find_section(artifact, "picks")

    if intro is None or how is None or picks is None:
        return False

    try:
        from agents.copy_editor_agent import CopyEditorAgent, CopyEditorConfig
        from integrations.openai_adapters import OpenAIJsonLLM
    except Exception:
        return False

    # Build editor inputs (body-only)
    title = request.topic.value.strip() or f"{request.intent.value}: {request.form.value}"
    audience = getattr(brand.audience.primary_audience, "value", str(brand.audience.primary_audience))
    category = request.domain.value

    intro_md = _blocks_to_markdown(intro.blocks)
    how_md = _blocks_to_markdown(how.blocks)

    products_payload: list[dict[str, Any]] = []
    for p in artifact.products or []:
        products_payload.append(
            {
                "pick_id": p.pick_id,
                "title": p.title,
                "url": p.url,
                "rating": p.rating,
                "reviews_count": p.reviews_count,
            }
        )

    picks_payload = [{"pick_id": p.pick_id, "body": ""} for p in artifact.products]

    editor = CopyEditorAgent(llm=OpenAIJsonLLM(), config=CopyEditorConfig(max_changes=25, max_pick_sentences=4))
    edited = editor.run(
        title=title,
        audience=audience,
        intro_md=intro_md,
        how_md=how_md,
        picks=picks_payload,
        products=products_payload,
        category=category,
    )

    # Apply edits back to artifact sections.
    _set_section_markdown(intro, str(edited.get("intro_md") or intro_md))
    _set_section_markdown(how, str(edited.get("how_md") or how_md))

    by_id: dict[str, str] = {}
    for it in (edited.get("picks") or []):
        if isinstance(it, dict):
            pid = str(it.get("pick_id") or "").strip()
            body = str(it.get("body") or "").strip()
            if pid:
                by_id[pid] = body

    pick_blocks: list[Block] = []
    for p in artifact.products:
        body = by_id.get(p.pick_id, "").strip()
        # Render each pick as a subheading + paragraph in a single markdown block.
        block_text = f"### {p.title}\n\n{body}".strip()
        pick_blocks.append(Block(type=BlockType.paragraph, text=block_text))

    picks.blocks = pick_blocks

    return True
