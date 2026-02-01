from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.hero_self_heal import HeroPaths, ensure_hero_assets_exist


class _RegenOut:
    def __init__(self, slug: str) -> None:
        base = f"/images/posts/{slug}"
        self.hero_image_path = f"{base}/hero.webp"
        self.hero_image_home_path = f"{base}/hero_home.webp"
        self.hero_image_card_path = f"{base}/hero_card.webp"
        self.hero_source_path = f"{base}/hero_source.webp"


class TestHeroSelfHeal(unittest.TestCase):
    def test_placeholder_is_treated_as_missing_and_regens(self) -> None:
        with TemporaryDirectory() as td:
            public_dir = Path(td)

            # placeholder
            placeholder = public_dir / "images" / "placeholder-hero.webp"
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            placeholder.write_bytes(b"PLACEHOLDER")

            slug = "test-slug"
            paths = HeroPaths.for_slug(slug)

            # Pre-fill expected hero files with placeholder bytes.
            for url_path in (paths.hero, paths.hero_home, paths.hero_card, paths.hero_source):
                disk = public_dir / url_path.lstrip("/")
                disk.parent.mkdir(parents=True, exist_ok=True)
                disk.write_bytes(b"PLACEHOLDER")

            def regen_fn(**kwargs):
                # Write non-placeholder bytes to all expected files.
                for url_path in (paths.hero, paths.hero_home, paths.hero_card, paths.hero_source):
                    disk = public_dir / url_path.lstrip("/")
                    disk.write_bytes(b"REGENERATED")
                return _RegenOut(slug)

            out_paths = ensure_hero_assets_exist(
                public_dir=public_dir,
                slug=slug,
                placeholder_url="/images/placeholder-hero.webp",
                regen_fn=regen_fn,
                regen_kwargs={},
            )

            self.assertEqual(out_paths, paths)

            # Verify hero.webp is no longer placeholder.
            hero_disk = public_dir / paths.hero.lstrip("/")
            self.assertEqual(hero_disk.read_bytes(), b"REGENERATED")
