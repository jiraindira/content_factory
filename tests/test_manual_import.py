from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from content_factory.manual_import import legacy_manual_to_request
from content_factory.validation import load_brand_profile, validate_request_against_brand


class TestManualImport(unittest.TestCase):
    def test_legacy_manual_to_request_the_product_wheel(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "the_product_wheel.yaml")

        legacy = {
            "category": "travel",
            "subcategory": "luggage",
            "audience": "UK shoppers",
            "seed_title": "Best Luggage for Travel: Top Picks for Every Budget",
            "seed_description": "Short seed description.",
            "products": [
                {
                    "name": "Example Carry-on",
                    "url": "https://amzn.to/example",
                    "rating": 4.5,
                    "reviews_count": 123,
                },
                {
                    "name": "Example Backpack",
                    "url": "https://www.amazon.co.uk/dp/example",
                    "rating": 4.6,
                    "reviews_count": 456,
                },
                {
                    "name": "Example Packing Cubes",
                    "url": "https://example.com/product",
                },
            ],
        }

        res = legacy_manual_to_request(
            brand=brand,
            legacy=legacy,
            publish_date=date(2099, 1, 1),
            run_id="manual_test",
        )
        req = res.request

        self.assertEqual(req.brand_id, "the_product_wheel")
        self.assertEqual(req.domain.value, "travel")
        self.assertEqual(req.topic.mode.value, "manual")
        self.assertIn(req.topic.value, brand.topic_policy.allowlist)
        self.assertEqual(req.title_override, legacy["seed_title"])
        self.assertEqual(req.description_override, legacy["seed_description"])
        self.assertEqual(req.audience_override, legacy["audience"])
        self.assertEqual(req.categories_override, ["travel"])
        self.assertEqual(req.products.mode.value, "manual_list")
        self.assertEqual(len(req.products.items), 3)

        validate_request_against_brand(brand=brand, request=req)
