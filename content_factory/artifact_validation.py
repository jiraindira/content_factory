from __future__ import annotations

from content_factory.artifact_models import ContentArtifact
from content_factory.models import BrandProfile, ContentRequest, ProductRecommendationForm


def validate_artifact_against_specs(*, brand: BrandProfile, request: ContentRequest, artifact: ContentArtifact) -> None:
    errors: list[str] = []

    if artifact.brand_id != brand.brand_id:
        errors.append("artifact.brand_id must match brand.brand_id")

    if artifact.intent != request.intent.value:
        errors.append("artifact.intent must match request.intent")

    if artifact.form != request.form.value:
        errors.append("artifact.form must match request.form")

    if artifact.domain != request.domain.value:
        errors.append("artifact.domain must match request.domain")

    is_product_form = isinstance(request.form, ProductRecommendationForm)
    if is_product_form and not artifact.products:
        errors.append("artifact.products must be present for product forms")
    if (not is_product_form) and artifact.products is not None:
        errors.append("artifact.products must be null for non-product forms")

    if brand.disclaimer_policy.required:
        # Minimal structural check: disclaimer text must appear somewhere in callout blocks.
        disclaimer = (brand.disclaimer_policy.disclaimer_text or "").strip()
        found = False
        for sec in artifact.sections:
            for block in sec.blocks:
                if block.type.value == "callout" and (block.text or "").strip() == disclaimer:
                    found = True
                    break
            if found:
                break
        if not found:
            errors.append("required disclaimer block not found in artifact")

    if errors:
        msg = "\n".join(f"- {e}" for e in errors)
        raise ValueError(f"Artifact validation failed:\n{msg}")
