from __future__ import annotations

import unittest
from pathlib import Path

from content_factory.artifact_validation import validate_artifact_against_specs
from content_factory.brand_context import BrandContextArtifact
from content_factory.compiler import compile_content_artifact
from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


class TestContentFactoryCompiler(unittest.TestCase):
    def test_compiles_thought_leadership_without_products(self) -> None:
        repo = Path(__file__).resolve().parents[1]

        brand = load_brand_profile(repo / "content_factory" / "brands" / "alisa_amouage.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml")
        validate_request_against_brand(brand=brand, request=req)

        # Use a minimal in-memory context artifact (no network).
        ctx = BrandContextArtifact(
            brand_id=brand.brand_id,
            generated_at="2026-02-01T00:00:00Z",
            fetch_user_agent="AIContentFactoryFetcher-1.0",
            sources=[],
            signals={"titles": [], "headings": [], "descriptions": [], "positioning_snippets": [], "key_terms": []},
        )

        artifact = compile_content_artifact(brand=brand, request=req, brand_context=ctx, run_id="run")
        self.assertIsNone(artifact.products)
        validate_artifact_against_specs(brand=brand, request=req, artifact=artifact)

    def test_compiles_product_run_with_products(self) -> None:
        repo = Path(__file__).resolve().parents[1]

        brand = load_brand_profile(repo / "content_factory" / "brands" / "everyday_buying_guide.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "everyday_buying_guide_2026-02-01.yaml")
        validate_request_against_brand(brand=brand, request=req)

        ctx = BrandContextArtifact(
            brand_id=brand.brand_id,
            generated_at="2026-02-01T00:00:00Z",
            fetch_user_agent="AIContentFactoryFetcher-1.0",
            sources=[],
            signals={"titles": [], "headings": [], "descriptions": [], "positioning_snippets": [], "key_terms": []},
        )

        artifact = compile_content_artifact(brand=brand, request=req, brand_context=ctx, run_id="run")
        self.assertIsNotNone(artifact.products)
        self.assertGreaterEqual(len(artifact.products or []), 1)
        validate_artifact_against_specs(brand=brand, request=req, artifact=artifact)
