from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from content_factory.models import (
    ContentIntent,
    ContentRequest,
    DeliveryChannel,
    DeliveryDestination,
    DeliveryTarget,
    Domain,
    ProductItem,
    ProductRecommendationForm,
    Products,
    ProductsMode,
    Publish,
    Topic,
    TopicMode,
)
from content_factory.models import BrandProfile


@dataclass(frozen=True)
class ManualImportResult:
    request: ContentRequest
    warnings: list[str]


def load_legacy_manual_post_input(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Legacy manual input JSON root must be an object")
    return raw


def _slugify(text: str) -> str:
    s = (text or "").lower().strip()
    s = s.replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def _is_valid_http_url(url: str) -> bool:
    if url is None:
        return False
    s = str(url).strip()
    if not s:
        return False
    parsed = urlparse(s)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _lower_clean_list(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for v in values:
        s = str(v or "").strip().lower()
        if s:
            out.append(s)
    return out


def _choose_topic_from_allowlist(*, allowlist: list[str], hints: list[str]) -> tuple[str, list[str]]:
    """Pick a topic from allowlist using simple matching.

    Returns: (topic_value, warnings)
    """
    warnings: list[str] = []

    cleaned_allow = [a.strip() for a in allowlist if (a or "").strip()]
    if not cleaned_allow:
        raise ValueError("brand.topic_policy.allowlist must not be empty")

    cleaned_hints = [h.strip() for h in hints if (h or "").strip()]

    # 1) Exact match (case-insensitive)
    allow_lower = {a.lower(): a for a in cleaned_allow}
    for h in cleaned_hints:
        if h.lower() in allow_lower:
            return allow_lower[h.lower()], warnings

    # 2) Substring match (case-insensitive)
    for h in cleaned_hints:
        hl = h.lower()
        for a in cleaned_allow:
            if hl and hl in a.lower():
                return a, warnings

    warnings.append(
        "Could not match manual category/subcategory to brand topic allowlist; falling back to first allowlist entry"
    )
    return cleaned_allow[0], warnings


def legacy_manual_to_request(
    *,
    brand: BrandProfile,
    legacy: dict[str, Any],
    publish_date: date,
    run_id: str,
    domain_fallback: Optional[Domain] = None,
) -> ManualImportResult:
    warnings: list[str] = []

    raw_categories = legacy.get("categories")
    raw_category = legacy.get("category")
    raw_subcategory = legacy.get("subcategory")

    categories_override: Optional[list[str]] = None
    if isinstance(raw_categories, list) and raw_categories:
        categories_override = _lower_clean_list(raw_categories)
    elif isinstance(raw_category, str) and raw_category.strip():
        categories_override = [raw_category.strip().lower()]

    category_s = str(raw_category or "").strip()
    subcategory_s = str(raw_subcategory or "").strip()

    # Domain mapping: prefer category if it maps directly to the enum.
    domain: Domain
    try:
        domain = Domain(category_s.strip().lower()) if category_s else brand.domain_primary
    except Exception:
        domain = domain_fallback or brand.domain_primary
        if category_s:
            warnings.append(f"Unknown category '{category_s}'; using domain '{domain.value}'")

    # Topic must be from allowlist (validation enforces this).
    topic_value, topic_warnings = _choose_topic_from_allowlist(
        allowlist=brand.topic_policy.allowlist,
        hints=[subcategory_s, category_s, str(legacy.get("seed_title") or "").strip()],
    )
    warnings.extend(topic_warnings)

    # Products
    raw_products = legacy.get("products")
    if not isinstance(raw_products, list) or not raw_products:
        raise ValueError("legacy manual input must contain a non-empty 'products' list")

    items: list[ProductItem] = []
    for idx, p in enumerate(raw_products, start=1):
        if not isinstance(p, dict):
            raise ValueError(f"products[{idx}] must be an object")

        title = (p.get("title") or p.get("name") or "").strip()
        if not title:
            raise ValueError(f"products[{idx}] must have 'name' or 'title'")

        url = str(p.get("url") or "").strip()
        if not _is_valid_http_url(url):
            raise ValueError(f"products[{idx}] url must be a fully-qualified http(s) URL")

        rating = p.get("rating")
        reviews_count = p.get("reviews_count")

        provider = None
        host = urlparse(url).netloc.lower()
        if "amazon." in host or "amzn." in host:
            provider = "amazon"

        items.append(
            ProductItem(
                pick_id=f"pick-{idx}-{_slugify(title)}",
                title=title,
                url=url,
                rating=float(rating) if rating is not None else None,
                reviews_count=int(reviews_count) if reviews_count is not None else None,
                provider=provider,
            )
        )

    req = ContentRequest(
        brand_id=brand.brand_id,
        publish=Publish(publish_date=publish_date),
        intent=ContentIntent.product_recommendation,
        form=ProductRecommendationForm.top_x_list,
        domain=domain,
        topic=Topic(mode=TopicMode.manual, value=topic_value),
        delivery_target=DeliveryTarget(
            destination=DeliveryDestination.hosted_by_us,
            channel=DeliveryChannel.blog_article,
        ),
        products=Products(mode=ProductsMode.manual_list, items=items),
        title_override=str(legacy.get("seed_title") or "").strip() or None,
        description_override=str(legacy.get("seed_description") or "").strip() or None,
        categories_override=categories_override,
        audience_override=str(legacy.get("audience") or "").strip() or None,
    )

    # Basic sanity: warn if requested domain isn’t supported by this brand.
    if req.domain not in brand.domains_supported:
        warnings.append(
            f"Domain '{req.domain.value}' is not supported by brand; you may need to update brand.domains_supported"
        )

    return ManualImportResult(request=req, warnings=warnings)
