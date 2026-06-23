from __future__ import annotations

from pathlib import Path

from content_factory.adapters.common import (
    RenderedDelivery,
    ensure_delivery_target_matches,
    extract_topic_from_artifact,
    section_to_plain_text,
)
from content_factory.artifact_models import ContentArtifact
from content_factory.models import BrandProfile, ContentRequest, DeliveryChannel, DeliveryDestination



def build_instagram_caption_from_artifact(*, artifact: ContentArtifact) -> str:
    """Build a simple Instagram caption from a ContentArtifact.

    Used by both the Instagram adapter and Content Package writer. This
    intentionally ignores the delivery target and brand so it can be reused
    when deriving social captions from a blog run.
    """

    topic = extract_topic_from_artifact(artifact)
    parts: list[str] = []

    if topic:
        parts.append(topic)

    # Add a short body from the first couple of sections.
    for sec in artifact.sections[:2]:
        t = section_to_plain_text(sec)
        if t:
            parts.append(t)

    caption = "\n\n".join([p.strip() for p in parts if p.strip()]).strip()
    return caption + "\n" if caption else ""


def render_instagram_caption(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> str:
    """Render a single Instagram caption from the artifact.

    v1 is intentionally simple and deterministic: topic + a short
    summary body. Any LLM-based refinement can be layered on later.
    """

    ensure_delivery_target_matches(
        target_channel=DeliveryChannel.social_shortform,
        target_destination=DeliveryDestination.instagram,
        actual_channel=request.delivery_target.channel,
        actual_destination=request.delivery_target.destination,
    )
    return build_instagram_caption_from_artifact(artifact=artifact)


def render_instagram_delivery(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> RenderedDelivery:
    filename = f"{artifact.run_id}.instagram.txt"
    caption = render_instagram_caption(brand=brand, request=request, artifact=artifact)
    return RenderedDelivery(filename=filename, mime_type="text/plain", content=caption)


def write_instagram_delivery(*, repo_root: Path, delivery: RenderedDelivery) -> Path:
    out_dir = repo_root / "content_factory" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / delivery.filename
    out_path.write_text(delivery.content, encoding="utf-8")
    return out_path
