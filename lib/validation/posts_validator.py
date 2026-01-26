from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.validation.markdown_frontmatter import (
    parse_markdown_frontmatter,
    rebuild_markdown_with_frontmatter,
)
from lib.validation.url_utils import normalize_url


@dataclass
class UrlIssue:
    file: Path
    product_index: int
    pick_id: str
    field_path: str
    message: str
    original: str
    normalized: Optional[str] = None


def _get_products(frontmatter: Dict[str, Any]) -> List[Dict[str, Any]]:
    products = frontmatter.get("products", [])
    if products is None:
        return []
    if not isinstance(products, list):
        raise ValueError("Frontmatter 'products' must be a list.")
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(products):
        if not isinstance(item, dict):
            raise ValueError(f"Frontmatter 'products[{i}]' must be an object.")
        out.append(item)
    return out


def validate_and_optionally_fix_post(md_path: Path, fix: bool) -> List[UrlIssue]:
    text = md_path.read_text(encoding="utf-8")
    parsed = parse_markdown_frontmatter(text)
    fm = parsed.data

    issues: List[UrlIssue] = []
    products = _get_products(fm)

    changed = False

    for idx, prod in enumerate(products):
        pick_id = str(prod.get("pick_id", "")).strip()
        url_raw = prod.get("url", "")

        try:
            res = normalize_url(url_raw)
            if fix and res.changed:
                prod["url"] = res.normalized
                changed = True
            elif (not fix) and res.changed:
                issues.append(
                    UrlIssue(
                        file=md_path,
                        product_index=idx,
                        pick_id=pick_id,
                        field_path=f"products.{idx}.url",
                        message="URL missing scheme; can be normalized safely",
                        original=str(url_raw),
                        normalized=res.normalized,
                    )
                )
        except Exception as e:
            issues.append(
                UrlIssue(
                    file=md_path,
                    product_index=idx,
                    pick_id=pick_id,
                    field_path=f"products.{idx}.url",
                    message=str(e),
                    original=str(url_raw),
                    normalized=None,
                )
            )

    if fix and changed:
        fm["products"] = products
        rebuilt = rebuild_markdown_with_frontmatter(fm, parsed.body)
        md_path.write_text(rebuilt, encoding="utf-8")

    return issues


def validate_posts_dir(posts_dir: Path, fix: bool) -> List[UrlIssue]:
    if not posts_dir.exists():
        raise FileNotFoundError(f"Posts directory not found: {posts_dir}")

    issues: List[UrlIssue] = []
    for md_path in sorted(posts_dir.glob("*.md")):
        issues.extend(validate_and_optionally_fix_post(md_path, fix=fix))
    return issues
