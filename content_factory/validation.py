from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from content_factory.models import (
    BrandProfile,
    ContentRequest,
    PersonaModifier,
    ProductRecommendationForm,
    ProductsMode,
)
from content_factory.schema_loader import load_illegal_matrix


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {p}")
    return data


def load_brand_profile(path: str | Path) -> BrandProfile:
    data = load_yaml_file(path)
    return BrandProfile.model_validate(data)


def load_content_request(path: str | Path) -> ContentRequest:
    data = load_yaml_file(path)
    return ContentRequest.model_validate(data)


def _matrix_disallows(matrix: dict[str, Any], section: str, left: str, right: str) -> bool:
    sec = matrix.get(section)
    if not isinstance(sec, dict):
        return False
    disallowed = sec.get(left)
    if not isinstance(disallowed, list):
        return False
    return right in disallowed


def validate_request_against_brand(*, brand: BrandProfile, request: ContentRequest) -> None:
    errors: list[str] = []

    if request.brand_id != brand.brand_id:
        errors.append(f"brand_id mismatch: request={request.brand_id} brand={brand.brand_id}")

    # Local system time validation: today-or-future.
    if request.publish.publish_date < date.today():
        errors.append("publish.publish_date must be today-or-future (local system time)")

    if request.domain not in brand.domains_supported:
        errors.append(
            f"domain {request.domain.value} is not supported by brand; supported="
            f"{[d.value for d in brand.domains_supported]}"
        )

    # Brand strategy allowlists.
    if request.intent not in brand.content_strategy.allowed_intents:
        errors.append(
            f"intent {request.intent.value} not allowed by brand; allowed="
            f"{[i.value for i in brand.content_strategy.allowed_intents]}"
        )

    if isinstance(request.form, ProductRecommendationForm):
        if request.form not in brand.content_strategy.allowed_product_recommendation_forms:
            errors.append(
                f"form {request.form.value} not allowed for product intent; allowed="
                f"{[f.value for f in brand.content_strategy.allowed_product_recommendation_forms]}"
            )
    else:
        if request.form not in brand.content_strategy.allowed_thought_leadership_forms:
            errors.append(
                f"form {request.form.value} not allowed for thought leadership; allowed="
                f"{[f.value for f in brand.content_strategy.allowed_thought_leadership_forms]}"
            )

    # Topic allowlist-only: any explicit topic must be from allowlist.
    allowlist = set(brand.topic_policy.allowlist)
    if not allowlist:
        errors.append("brand.topic_policy.allowlist must not be empty")
    else:
        if request.topic.mode.value == "manual":
            if request.topic.value not in allowlist:
                errors.append("topic.value must be in brand.topic_policy.allowlist")
        else:
            # auto: if value is pre-specified, it must still be in allowlist
            if request.topic.value is not None and request.topic.value not in allowlist:
                errors.append("topic.value must be in brand.topic_policy.allowlist")

    # Delivery policy must be subset of brand.
    if request.delivery_target.channel not in brand.delivery_policy.delivery_channels:
        errors.append(
            f"delivery_target.channel {request.delivery_target.channel.value} not allowed by brand"
        )
    if request.delivery_target.destination not in brand.delivery_policy.delivery_destinations:
        errors.append(
            f"delivery_target.destination {request.delivery_target.destination.value} not allowed by brand"
        )

    # Products: v1 manual links only; only allowed for product recommendation forms.
    if isinstance(request.form, ProductRecommendationForm):
        if request.products.mode != ProductsMode.manual_list:
            errors.append("products.mode must be manual_list for product recommendation forms (v1)")
    else:
        if request.products.mode != ProductsMode.none:
            errors.append("products.mode must be none for non-product forms")

    # Illegal matrix enforcement (data-driven).
    matrix = load_illegal_matrix()

    form_value = request.form.value
    if _matrix_disallows(matrix, "intent_x_form", request.intent.value, form_value):
        errors.append(f"illegal_matrix intent_x_form violation: {request.intent.value} x {form_value}")

    persona_cfg = brand.persona_by_domain.get(request.domain)
    if persona_cfg is not None:
        persona_value = persona_cfg.primary_persona.value

        if _matrix_disallows(matrix, "persona_x_form", persona_value, form_value):
            errors.append(f"illegal_matrix persona_x_form violation: {persona_value} x {form_value}")

        posture_value = brand.commercial_policy.commercial_posture.value
        if _matrix_disallows(matrix, "persona_x_commercial_posture", persona_value, posture_value):
            errors.append(
                f"illegal_matrix persona_x_commercial_posture violation: {persona_value} x {posture_value}"
            )

        if _matrix_disallows(matrix, "domain_x_persona", request.domain.value, persona_value):
            errors.append(f"illegal_matrix domain_x_persona violation: {request.domain.value} x {persona_value}")

        depth_value = brand.content_strategy.default_content_depth.value
        channel_value = request.delivery_target.channel.value
        if _matrix_disallows(matrix, "depth_x_channel", depth_value, channel_value):
            errors.append(f"illegal_matrix depth_x_channel violation: {depth_value} x {channel_value}")

        dest_value = request.delivery_target.destination.value
        if _matrix_disallows(matrix, "destination_x_posture", dest_value, posture_value):
            errors.append(
                f"illegal_matrix destination_x_posture violation: {dest_value} x {posture_value}"
            )

        if _matrix_disallows(matrix, "destination_x_depth", dest_value, depth_value):
            errors.append(f"illegal_matrix destination_x_depth violation: {dest_value} x {depth_value}")

        # Modifier constraints (ignoring 'none').
        for modifier in persona_cfg.persona_modifiers:
            if modifier == PersonaModifier.none:
                continue
            if _matrix_disallows(matrix, "persona_x_modifier", persona_value, modifier.value):
                errors.append(
                    f"illegal_matrix persona_x_modifier violation: {persona_value} x {modifier.value}"
                )

    if errors:
        msg = "\n".join(f"- {e}" for e in errors)
        raise ValueError(f"Config validation failed:\n{msg}")
