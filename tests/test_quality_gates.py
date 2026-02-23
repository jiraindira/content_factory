from __future__ import annotations

import argparse
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from content_factory.adapters.blog_adapter import render_astro_markdown
from content_factory.artifact_models import Block, BlockType, Checks, ContentArtifact, Rationale, Section
from content_factory.channel_qa import validate_artifact_against_channel_specs
from content_factory.cli import cmd_import_manual
from content_factory.manual_import import legacy_manual_to_request
from content_factory.validation import load_brand_profile, validate_request_against_brand


class TestQualityGates(unittest.TestCase):
    def test_manual_import_requires_openai_key(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand_path = repo / "content_factory" / "brands" / "the_product_wheel.yaml"
        brand = load_brand_profile(brand_path)

        legacy = {
            "category": "travel",
            "subcategory": "Insulated drinkware",
            "audience": "UK shoppers",
            "seed_title": "Test Title",
            "seed_description": "Seed.",
            "products": [
                {
                    "name": "Example",
                    "url": "https://example.com/product",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            legacy_path = td_path / "post_input.json"
            legacy_path.write_text(__import__("json").dumps(legacy), encoding="utf-8")
            request_out = td_path / "request.yaml"

            args = argparse.Namespace(
                brand=str(brand_path),
                input=str(legacy_path),
                publish_date=str(date(2099, 1, 1)),
                run_id="manual_test_run",
                request_out=str(request_out),
                build_context_if_missing=False,
                write_package=False,
            )

            # Must hard-fail if OPENAI_API_KEY is not set.
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("OPENAI_API_KEY", None)
                with self.assertRaises(RuntimeError):
                    _ = cmd_import_manual(args)

    def test_manual_blog_pick_copy_quality_gates(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "the_product_wheel.yaml")

        legacy = {
            "category": "travel",
            "subcategory": "Travel gear and luggage",
            "audience": "UK shoppers",
            "seed_title": "Test Title",
            "seed_description": "Seed.",
            "products": [
                {
                    "name": "Example Carry-on",
                    "url": "https://example.com/carryon",
                    "rating": 4.6,
                    "reviews_count": 123,
                }
            ],
        }

        res = legacy_manual_to_request(brand=brand, legacy=legacy, publish_date=date(2099, 1, 1), run_id="x")
        req = res.request
        validate_request_against_brand(brand=brand, request=req)

        disclaimer = (brand.disclaimer_policy.disclaimer_text or "").strip()

        artifact = ContentArtifact(
            brand_id=brand.brand_id,
            run_id="x",
            generated_at="2099-01-01T00:00:00Z",
            intent=req.intent.value,
            form=req.form.value,
            domain=req.domain.value,
            content_depth=brand.content_strategy.default_content_depth.value,
            audience={"primary_audience": "general_consumers", "audience_sophistication": "medium"},
            persona={
                "primary_persona": "practical_expert",
                "persona_modifiers": [],
                "science_explicitness": "implied",
                "personal_presence": "none",
                "narration_mode": "third_person_only",
            },
            sections=[
                Section(
                    id="intro",
                    heading=None,
                    blocks=[
                        Block(type=BlockType.paragraph, text=f"Topic: {req.topic.value}"),
                        Block(type=BlockType.paragraph, text="Intro paragraph."),
                    ],
                ),
                Section(
                    id="how_chosen",
                    heading="How this list was chosen",
                    blocks=[Block(type=BlockType.paragraph, text="How chosen."),
                    ],
                ),
                Section(
                    id="picks",
                    heading="Top picks",
                    blocks=[
                        Block(
                            type=BlockType.paragraph,
                            text="A solid option.\n\nMentions reviews which should be blocked.",
                            meta={"pick_id": "pick-1-example-carry-on"},
                        )
                    ],
                ),
                Section(
                    id="closing",
                    heading="Closing",
                    blocks=[
                        Block(type=BlockType.paragraph, text="Disclosure paragraph."),
                        Block(type=BlockType.callout, text=disclaimer),
                    ],
                ),
            ],
            products=[
                {
                    "pick_id": "pick-1-example-carry-on",
                    "title": "Example Carry-on",
                    "url": "https://example.com/carryon",
                    "rating": 4.6,
                    "reviews_count": 123,
                    "provider": None,
                }
            ],
            rationale=Rationale(how_chosen_blocks=[], selection_criteria=[]),
            claims=[
                {
                    "id": "clm_1",
                    "text": "x",
                    "claim_type": "advice",
                    "requires_citation": False,
                    "supported_by_source_ids": [],
                }
            ],
            sources=[],
            checks=Checks(
                matrix_validation_passed=True,
                brand_policy_checks_passed=True,
                required_sections_present=True,
                products_present_when_required=True,
                citations_present_when_required=True,
                topic_allowlist_passed=True,
                required_disclaimers_present=True,
                robots_policy_passed=True,
                disallowed_claims_found=[],
            ),
        )

        with self.assertRaises(ValueError) as ctx:
            validate_artifact_against_channel_specs(brand=brand, request=req, artifact=artifact)
        msg = str(ctx.exception)
        self.assertIn("Skip it if", msg)
        self.assertIn("reviews", msg.lower())

        # Fix pick body to satisfy gates.
        artifact.sections[2].blocks[0].text = "Why it\u2019s included.\n\nSkip it if you want something smaller."
        validate_artifact_against_channel_specs(brand=brand, request=req, artifact=artifact)

    def test_blog_output_has_no_closing_header(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "the_product_wheel.yaml")

        legacy = {
            "category": "travel",
            "subcategory": "Travel gear and luggage",
            "audience": "UK shoppers",
            "seed_title": "Test Title",
            "seed_description": "Seed.",
            "products": [
                {
                    "name": "Example Carry-on",
                    "url": "https://example.com/carryon",
                }
            ],
        }

        req = legacy_manual_to_request(brand=brand, legacy=legacy, publish_date=date(2099, 1, 1), run_id="x").request
        validate_request_against_brand(brand=brand, request=req)

        disclaimer = (brand.disclaimer_policy.disclaimer_text or "").strip()

        artifact = ContentArtifact(
            brand_id=brand.brand_id,
            run_id="x",
            generated_at="2099-01-01T00:00:00Z",
            intent=req.intent.value,
            form=req.form.value,
            domain=req.domain.value,
            content_depth=brand.content_strategy.default_content_depth.value,
            audience={"primary_audience": "general_consumers", "audience_sophistication": "medium"},
            persona={
                "primary_persona": "practical_expert",
                "persona_modifiers": [],
                "science_explicitness": "implied",
                "personal_presence": "none",
                "narration_mode": "third_person_only",
            },
            sections=[
                Section(
                    id="intro",
                    heading=None,
                    blocks=[
                        Block(type=BlockType.paragraph, text=f"Topic: {req.topic.value}"),
                        Block(type=BlockType.paragraph, text="Intro paragraph."),
                    ],
                ),
                Section(
                    id="picks",
                    heading="Top picks",
                    blocks=[
                        Block(
                            type=BlockType.paragraph,
                            text="Why it\u2019s included.\n\nSkip it if you want something else.",
                            meta={"pick_id": "pick-1-example-carry-on"},
                        )
                    ],
                ),
                Section(
                    id="closing",
                    heading="Closing",
                    blocks=[
                        Block(type=BlockType.paragraph, text="Disclosure paragraph."),
                        Block(type=BlockType.callout, text=disclaimer),
                    ],
                ),
            ],
            products=[
                {
                    "pick_id": "pick-1-example-carry-on",
                    "title": "Example Carry-on",
                    "url": "https://example.com/carryon",
                    "rating": None,
                    "reviews_count": None,
                    "provider": None,
                }
            ],
            rationale=Rationale(how_chosen_blocks=[], selection_criteria=[]),
            claims=[
                {
                    "id": "clm_1",
                    "text": "x",
                    "claim_type": "advice",
                    "requires_citation": False,
                    "supported_by_source_ids": [],
                }
            ],
            sources=[],
            checks=Checks(
                matrix_validation_passed=True,
                brand_policy_checks_passed=True,
                required_sections_present=True,
                products_present_when_required=True,
                citations_present_when_required=True,
                topic_allowlist_passed=True,
                required_disclaimers_present=True,
                robots_policy_passed=True,
                disallowed_claims_found=[],
            ),
        )

        out = render_astro_markdown(brand=brand, request=req, artifact=artifact)
        self.assertNotIn("## Closing", out)
