from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class ContentPackagePaths:
    package_dir: Path
    manifest_path: Path
    post_path: Path


def _slugify(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "post"


def write_content_package_v1(
    *,
    repo_root: Path,
    brand_id: str,
    run_id: str,
    publish_date: date,
    slug_source: str,
    post_markdown: str,
) -> ContentPackagePaths:
    """Write Content Package v1.

    Layout:
      content_factory/packages/{brand_id}/{run_id}/
        manifest.json
        post.md

    `slug_source` is slugified into manifest.slug.
    """

    packages_dir = repo_root / "content_factory" / "packages" / brand_id / run_id
    packages_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(slug_source)

    manifest = {
        "version": "1",
        "brand_id": brand_id,
        "run_id": run_id,
        "publish_date": publish_date.isoformat(),
        "slug": slug,
        "outputs": [
            {
                "type": "post",
                "path": "post.md",
            }
        ],
    }

    manifest_path = packages_dir / "manifest.json"
    post_path = packages_dir / "post.md"

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    post_path.write_text((post_markdown or "").rstrip() + "\n", encoding="utf-8")

    return ContentPackagePaths(package_dir=packages_dir, manifest_path=manifest_path, post_path=post_path)
