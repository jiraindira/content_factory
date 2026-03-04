from __future__ import annotations

import argparse
from pathlib import Path

from managed_site.hydration import hydrate_blog_post_from_package


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply a Content Package v1 into the managed Astro site")
    ap.add_argument("--package-dir", required=True, help="Path to content_factory/packages/<brand_id>/<run_id>")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing post if present")
    ap.add_argument("--no-pick-images", action="store_true", help="Skip pick image enrichment")
    ap.add_argument("--dry-run", action="store_true", help="Skip networked hydration steps (still writes the post)")
    ap.add_argument(
        "--no-hero-regen",
        action="store_true",
        help="Do not attempt hero regeneration even if OPENAI_API_KEY is set (uses placeholder)",
    )

    args = ap.parse_args(argv)

    repo_root = _repo_root()
    package_dir = Path(args.package_dir)
    if not package_dir.is_absolute():
        package_dir = repo_root / package_dir

    res = hydrate_blog_post_from_package(
        repo_root=repo_root,
        package_dir=package_dir,
        overwrite=bool(args.overwrite),
        enrich_pick_images=not bool(args.no_pick_images),
        dry_run=bool(args.dry_run),
        regen_hero_if_possible=not bool(args.no_hero_regen),
    )

    print(f"Applied package: {res.package_dir}")
    print(f"Wrote post: {res.post_path}")
    print(f"Hero: {res.hero_paths.get('heroImage')}")
    if not args.no_pick_images:
        print(f"Pick images: updated={res.pick_images_updated} skipped={res.pick_images_skipped}")
        if res.pick_image_errors:
            print("Pick image errors:")
            for e in res.pick_image_errors:
                print(f"- {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
