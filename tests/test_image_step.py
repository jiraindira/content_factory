from __future__ import annotations

import unittest

from pipeline.image_step import generate_hero_image
from schemas.hero_image import HeroImageRequest


class _FakeImageAgent:
    def run(self, req: HeroImageRequest):
        # If the bug regresses and a dict is passed, this will fail loudly.
        if not isinstance(req, HeroImageRequest):
            raise TypeError(f"expected HeroImageRequest, got {type(req)}")

        class _Out:
            hero_image_path = f"/images/posts/{req.slug}/hero.webp"
            hero_image_home_path = f"/images/posts/{req.slug}/hero_home.webp"
            hero_image_card_path = f"/images/posts/{req.slug}/hero_card.webp"
            hero_source_path = f"/images/posts/{req.slug}/hero_source.webp"
            hero_alt = "alt"

        return _Out()


class TestImageStep(unittest.TestCase):
    def test_generate_hero_image_passes_request_model(self) -> None:
        out = generate_hero_image(
            agent=_FakeImageAgent(),
            slug="my-slug",
            category="home",
            title="My Title",
            intro="Intro text",
            picks=["Pick one"],
            alternatives=None,
        )
        self.assertIn("/images/posts/my-slug/hero.webp", out.hero_image_path)
