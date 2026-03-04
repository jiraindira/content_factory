from __future__ import annotations

from pathlib import Path

import yaml

from content_factory.adapters.blog_adapter import render_astro_markdown
from content_factory.brand_context import BrandContextArtifact
from content_factory.compiler import compile_content_artifact
from content_factory.generation import generate_filled_artifact
from content_factory.models import DeliveryChannel, DeliveryDestination
from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


def _ctx(brand_id: str) -> BrandContextArtifact:
    return BrandContextArtifact(
        brand_id=brand_id,
        generated_at="2099-01-01T00:00:00Z",
        fetch_user_agent="AIContentFactoryFetcher-1.0",
        sources=[],
        signals={"titles": [], "headings": [], "descriptions": [], "positioning_snippets": [], "key_terms": []},
    )


def _frontmatter_dict(md: str) -> dict:
    text = (md or "")
    assert text.startswith("---\n")
    end = text.find("\n---\n", 4)
    assert end != -1
    fm_text = text[4:end]
    data = yaml.safe_load(fm_text) or {}
    assert isinstance(data, dict)
    return data


def test_blog_adapter_includes_picks_frontmatter_for_products() -> None:
    repo = Path(__file__).resolve().parents[1]
    brand = load_brand_profile(repo / "content_factory" / "brands" / "everyday_buying_guide.yaml")
    req = load_content_request(repo / "content_factory" / "requests" / "everyday_buying_guide_2026-02-01.yaml")

    req.delivery_target.channel = DeliveryChannel.blog_article
    req.delivery_target.destination = DeliveryDestination.hosted_by_us

    validate_request_against_brand(brand=brand, request=req)

    artifact = compile_content_artifact(brand=brand, request=req, brand_context=_ctx(brand.brand_id), run_id="run")
    generate_filled_artifact(brand=brand, request=req, artifact=artifact)

    md = render_astro_markdown(brand=brand, request=req, artifact=artifact)
    fm = _frontmatter_dict(md)

    assert "picks" in fm
    assert isinstance(fm["picks"], list)
    # Should have same number of picks as products, even if bodies are empty.
    assert len(fm["picks"]) == len(fm["products"])
    assert all("pick_id" in p for p in fm["picks"])
