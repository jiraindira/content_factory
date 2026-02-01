from __future__ import annotations

import unittest
from pathlib import Path

from content_factory.brand_context import BrandContextArtifact
from content_factory.compiler import compile_content_artifact
from content_factory.generation import GenerationPath, generate_filled_artifact, route_generation_path
from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


def _artifact_text(artifact) -> str:
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


class TestContentFactoryGeneration(unittest.TestCase):
    def test_routing_is_deterministic(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        req = load_content_request(repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml")
        self.assertEqual(route_generation_path(request=req), GenerationPath.thought_leadership)

        req2 = load_content_request(repo / "content_factory" / "requests" / "everyday_buying_guide_2026-02-01.yaml")
        self.assertEqual(route_generation_path(request=req2), GenerationPath.product_recommendation)

    def test_thought_leadership_contains_no_buying_guide_language(self) -> None:
        repo = Path(__file__).resolve().parents[1]

        brand = load_brand_profile(repo / "content_factory" / "brands" / "alisa_amouage.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml")
        validate_request_against_brand(brand=brand, request=req)

        ctx = BrandContextArtifact(
            brand_id=brand.brand_id,
            generated_at="2026-02-01T00:00:00Z",
            fetch_user_agent="AIContentFactoryFetcher-1.0",
            sources=[],
            signals={"titles": [], "headings": [], "descriptions": [], "positioning_snippets": [], "key_terms": []},
        )

        artifact = compile_content_artifact(brand=brand, request=req, brand_context=ctx, run_id="run")
        report = generate_filled_artifact(brand=brand, request=req, artifact=artifact)
        self.assertEqual(report.path, GenerationPath.thought_leadership)

        self.assertGreaterEqual(len(artifact.claims), 1)

        text = _artifact_text(artifact).lower()
        for bad in ["amazon", "affiliate", "what to buy", "buying guide", "buyers guide", "picks", "buy now"]:
            self.assertNotIn(bad, text)

        claims_text = "\n".join(c.text for c in artifact.claims).lower()
        for bad in ["amazon", "affiliate", "what to buy", "buying guide", "buyers guide", "picks", "buy now"]:
            self.assertNotIn(bad, claims_text)

    def test_product_recommendation_includes_products_in_picks(self) -> None:
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
        report = generate_filled_artifact(brand=brand, request=req, artifact=artifact)
        self.assertEqual(report.path, GenerationPath.product_recommendation)

        self.assertGreaterEqual(len(artifact.claims), 1)

        self.assertIsNotNone(artifact.products)
        self.assertGreaterEqual(len(artifact.products or []), 1)

        text = _artifact_text(artifact)
        for p in artifact.products or []:
            self.assertIn(p.title, text)
            self.assertIn(p.url, text)
