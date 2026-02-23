from __future__ import annotations

import re
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


def _normalize_markdown_bullets(md: str) -> str:
    """Normalize common bullet glyphs into Markdown '-' list items.

    Astro/marked won't treat '•' as a list marker, so we convert it.
    """

    text = (md or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    # If the model emits '• ' bullets, normalize to '- '.
    lines = [ln.strip() for ln in text.split("\n")]
    has_dot_bullets = any(ln.startswith("•") for ln in lines)
    if has_dot_bullets:
        norm_lines: list[str] = []
        for ln in lines:
            if not ln:
                continue
            if ln.startswith("•"):
                norm_lines.append("- " + ln.lstrip("•").strip())
            else:
                norm_lines.append(ln)
        text = "\n".join(norm_lines).strip()

    # If bullets are inline (e.g., "• A. • B."), split into separate list items.
    if "•" in text and not re.search(r"^\s*[-*]\s+", text, flags=re.MULTILINE):
        parts = [p.strip() for p in text.split("•") if p.strip()]
        if len(parts) >= 2:
            text = "\n".join(["- " + p.lstrip("-").strip() for p in parts]).strip()

    return text


def apply_copy_editor_to_artifact_if_applicable(
    *,
    brand: BrandProfile,
    request: ContentRequest,
    artifact: ContentArtifact,
    require: bool = False,
) -> bool:
    """Body-only editorial pass for product recommendation artifacts.

    Returns True if edits were applied, False if skipped.
    """

    if request.intent != ContentIntent.product_recommendation:
        if require:
            raise ValueError("LLM editorial is required but request is not product_recommendation")
        return False

    # Only apply when products exist; editor uses product titles to craft pick bodies.
    if not artifact.products:
        if require:
            raise ValueError("LLM editorial is required but artifact has no products")
        return False

    intro = _find_section(artifact, "intro")
    how = _find_section(artifact, "how_chosen")
    picks = _find_section(artifact, "picks")

    if intro is None or how is None or picks is None:
        if require:
            raise ValueError("LLM editorial is required but intro/how_chosen/picks sections are missing")
        return False

    try:
        from agents.copy_editor_agent import CopyEditorAgent, CopyEditorConfig
        from integrations.openai_adapters import OpenAIJsonLLM
    except Exception as e:
        if require:
            raise
        return False

    # Build editor inputs (body-only)
    title = request.topic.value.strip() or f"{request.intent.value}: {request.form.value}"
    audience = getattr(brand.audience.primary_audience, "value", str(brand.audience.primary_audience))
    category = request.domain.value

    topic_blocks: list[Block] = []
    intro_blocks_for_edit: list[Block] = []
    for b in intro.blocks or []:
        if b.type == BlockType.paragraph and (b.text or "").strip().lower().startswith("topic:"):
            topic_blocks.append(b)
        else:
            intro_blocks_for_edit.append(b)

    intro_md = _blocks_to_markdown(intro_blocks_for_edit)
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

    editor = CopyEditorAgent(llm=OpenAIJsonLLM(), config=CopyEditorConfig(max_changes=25, max_pick_sentences=6))
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
    edited_intro_md = str(edited.get("intro_md") or intro_md).strip()
    intro.blocks = list(topic_blocks) + [Block(type=BlockType.paragraph, text=edited_intro_md)]
    how_out = str(edited.get("how_md") or how_md)
    how_out = _normalize_markdown_bullets(how_out)
    _set_section_markdown(how, how_out)

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
        pick_blocks.append(Block(type=BlockType.paragraph, text=body, meta={"pick_id": p.pick_id}))

    picks.blocks = pick_blocks

    return True
