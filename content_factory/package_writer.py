from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from lib.product_catalog import slugify_key


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ContentPackageWriteResult:
    package_dir: Path
    manifest_path: Path
    post_path: Path
    slug: str


def _extract_yaml_frontmatter(md: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter from a markdown string.

    Returns (frontmatter_dict, body_markdown).

    If no frontmatter is present, returns ({}, original_md).
    """

    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        return {}, text

    # Find the closing '---' delimiter.
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    fm_text = text[4:end]
    body = text[end + len("\n---\n") :]

    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        return {}, text

    return fm, body


def write_content_package_v1(
    *,
    repo_root: Path,
    brand_id: str,
    run_id: str,
    publish_date: date,
    post_markdown: str,
) -> ContentPackageWriteResult:
    """Write Content Package v1 to content_factory/packages/{brand_id}/{run_id}.

    Writes:
      - manifest.json
      - post.md
    """

    fm, _ = _extract_yaml_frontmatter(post_markdown)
    title = str(fm.get("title") or "").strip()

    slug = slugify_key(title) if title else slugify_key(run_id)
    if not slug:
        slug = "run"

    package_dir = repo_root / "content_factory" / "packages" / brand_id / run_id
    package_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "version": "1",
        "brand_id": brand_id,
        "run_id": run_id,
        "created_at": _utc_now_iso(),
        "publish_date": publish_date.isoformat(),
        "slug": slug,
        "outputs": [
            {
                "kind": "blog_post",
                "path": "post.md",
            }
        ],
    }

    manifest_path = package_dir / "manifest.json"
    post_path = package_dir / "post.md"

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    post_path.write_text((post_markdown or "").rstrip() + "\n", encoding="utf-8")

    return ContentPackageWriteResult(
        package_dir=package_dir,
        manifest_path=manifest_path,
        post_path=post_path,
        slug=slug,
    )
