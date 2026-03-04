from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from content_factory.package_writer import write_content_package_v1
from managed_site.hydration import hydrate_blog_post_from_package
from lib.validation.markdown_frontmatter import parse_markdown_frontmatter


def test_hydrate_blog_post_from_package_writes_post_and_hero(tmp_path: Path) -> None:
    repo_root = tmp_path

    # Minimal managed-site structure + placeholder hero.
    (repo_root / "site" / "src" / "content" / "posts").mkdir(parents=True, exist_ok=True)
    placeholder = repo_root / "site" / "public" / "images" / "placeholder-hero.webp"
    placeholder.parent.mkdir(parents=True, exist_ok=True)
    placeholder.write_bytes(b"placeholder")

    md = """---\ntitle: My Title\ndescription: x\npublishedAt: 2099-01-01\ncategories: [tech]\nproducts: []\npicks: []\n---\n\n## Intro\n\nHello\n"""

    pkg = write_content_package_v1(
        repo_root=repo_root,
        brand_id="the_product_wheel",
        run_id="run1",
        publish_date=date(2099, 1, 1),
        post_markdown=md,
    )

    out = hydrate_blog_post_from_package(
        repo_root=repo_root,
        package_dir=pkg.package_dir,
        overwrite=False,
        enrich_pick_images=False,
        dry_run=True,
        regen_hero_if_possible=False,
    )

    assert out.post_slug == "2099-01-01-my-title"
    assert out.post_path.exists()

    # Hero assets should have been backfilled with placeholder.
    hero_disk = repo_root / "site" / "public" / out.hero_paths["heroImage"].lstrip("/")
    assert hero_disk.exists()

    # Manifest should still be valid JSON.
    manifest = json.loads((pkg.package_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1"


def test_hydration_overwrite_preserves_existing_product_images(tmp_path: Path) -> None:
    repo_root = tmp_path

    (repo_root / "site" / "src" / "content" / "posts").mkdir(parents=True, exist_ok=True)
    placeholder = repo_root / "site" / "public" / "images" / "placeholder-hero.webp"
    placeholder.parent.mkdir(parents=True, exist_ok=True)
    placeholder.write_bytes(b"placeholder")

    # First, create an existing post that already has an enriched product image.
    existing_md = """---\ntitle: My Title\ndescription: x\npublishedAt: 2099-01-01\ncategories: [tech]\nproducts:\n- pick_id: a\n  title: A\n  url: https://example.com\n  image: /images/picks/somewhere/a.jpg\npicks: []\n---\n\nHi\n"""
    post_path = repo_root / "site" / "src" / "content" / "posts" / "2099-01-01-my-title.md"
    post_path.write_text(existing_md, encoding="utf-8")

    # Package content lacks products[].image (factory content-only).
    pkg_md = """---\ntitle: My Title\ndescription: x\npublishedAt: 2099-01-01\ncategories: [tech]\nproducts:\n- pick_id: a\n  title: A\n  url: https://example.com\npicks: []\n---\n\nHi\n"""
    pkg = write_content_package_v1(
        repo_root=repo_root,
        brand_id="the_product_wheel",
        run_id="run2",
        publish_date=date(2099, 1, 1),
        post_markdown=pkg_md,
    )

    hydrate_blog_post_from_package(
        repo_root=repo_root,
        package_dir=pkg.package_dir,
        overwrite=True,
        enrich_pick_images=False,
        dry_run=True,
        regen_hero_if_possible=False,
    )

    parsed = parse_markdown_frontmatter(post_path.read_text(encoding="utf-8"))
    products = parsed.data.get("products")
    assert isinstance(products, list)
    assert products and isinstance(products[0], dict)
    assert products[0].get("image") == "/images/picks/somewhere/a.jpg"
