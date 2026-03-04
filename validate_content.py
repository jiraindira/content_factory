from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

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


@dataclass
class ValidationIssue:
    severity: Literal["error", "warning"]
    file: Path
    field_path: str
    message: str


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


def _is_http_url(s: str) -> bool:
    lowered = s.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _validate_public_asset_path(
    *,
    issues: List[ValidationIssue],
    md_path: Path,
    field: str,
    value: Any,
    public_dir: Path,
) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        issues.append(
            ValidationIssue(
                severity="error",
                file=md_path,
                field_path=field,
                message=f"Expected a string, got {type(value).__name__}",
            )
        )
        return

    s = value.strip()
    if not s:
        return

    # Remote images are allowed.
    if _is_http_url(s):
        return

    # Public paths should start with '/'.
    if not s.startswith("/"):
        issues.append(
            ValidationIssue(
                severity="warning",
                file=md_path,
                field_path=field,
                message="Image path is not an absolute public path ('/...'); skipping existence check",
            )
        )
        return

    abs_path = public_dir / s.lstrip("/")
    if not abs_path.exists():
        issues.append(
            ValidationIssue(
                severity="error",
                file=md_path,
                field_path=field,
                message=f"Referenced public asset does not exist: {s}",
            )
        )


def validate_and_optionally_fix_post(md_path: Path, fix: bool) -> List[UrlIssue]:
    """
    Validates product URLs inside a post's frontmatter.

    Current policy:
      - url == "" (or whitespace) is allowed (link pending)
      - non-empty urls must be valid http(s) URLs
      - when fix=True, safe normalizations are applied (e.g., prefix https:// for 'www.')
      - malformed non-empty urls hard-fail (reported as fatal issues)
    """
    text = md_path.read_text(encoding="utf-8")
    parsed = parse_markdown_frontmatter(text)
    fm = parsed.data

    issues: List[UrlIssue] = []
    products = _get_products(fm)

    changed = False

    for idx, prod in enumerate(products):
        pick_id = str(prod.get("pick_id", "")).strip()
        url_raw = prod.get("url", "")
        url_str = "" if url_raw is None else str(url_raw).strip()

        # ✅ Allow blank URLs (link pending)
        if url_str == "":
            continue

        try:
            res = normalize_url(url_str)

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
                        original=url_str,
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
                    original=url_str,
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


def validate_post_frontmatter_contracts(
    *,
    md_path: Path,
    public_dir: Path,
    fix: bool,
) -> List[ValidationIssue]:
    text = md_path.read_text(encoding="utf-8")
    parsed = parse_markdown_frontmatter(text)
    fm = parsed.data

    issues: List[ValidationIssue] = []

    # Hero image variants: if present and public, ensure they exist.
    for key in ("heroImage", "heroImageHome", "heroImageCard", "heroImageSource"):
        _validate_public_asset_path(
            issues=issues,
            md_path=md_path,
            field=key,
            value=fm.get(key),
            public_dir=public_dir,
        )

    if fm.get("heroImage") and not fm.get("heroAlt"):
        issues.append(
            ValidationIssue(
                severity="warning",
                file=md_path,
                field_path="heroAlt",
                message="heroAlt is missing; screen readers will fall back to the title",
            )
        )

    # Products / picks contracts
    products = _get_products(fm)
    if products:
        seen_pick_ids: set[str] = set()
        for idx, prod in enumerate(products):
            pick_id = str(prod.get("pick_id", "") or "").strip()
            title = str(prod.get("title", "") or "").strip()

            if not pick_id:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        file=md_path,
                        field_path=f"products.{idx}.pick_id",
                        message="pick_id is required for every product",
                    )
                )
            elif pick_id in seen_pick_ids:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        file=md_path,
                        field_path=f"products.{idx}.pick_id",
                        message=f"Duplicate pick_id within post: {pick_id}",
                    )
                )
            else:
                seen_pick_ids.add(pick_id)

            if not title:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        file=md_path,
                        field_path=f"products.{idx}.title",
                        message="title is required for every product",
                    )
                )

        # URL checks + optional fixes (reuses existing URL normalizer)
        url_issues = validate_and_optionally_fix_post(md_path, fix=fix)
        for ui in url_issues:
            # Invalid URLs are treated as errors; normalizable URLs are warnings.
            sev: Literal["error", "warning"] = "warning" if ui.normalized else "error"
            issues.append(
                ValidationIssue(
                    severity=sev,
                    file=ui.file,
                    field_path=ui.field_path,
                    message=ui.message,
                )
            )

    return issues


def _print_issues(issues: List[ValidationIssue]) -> None:
    for it in issues:
        rel = it.file.as_posix()
        print(f"[{it.severity}] {rel} :: {it.field_path} :: {it.message}")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate site content contracts")
    parser.add_argument("--fix", action="store_true", help="Apply safe normalizations (e.g., URL scheme)")
    parser.add_argument(
        "--posts-dir",
        type=str,
        default=None,
        help="Override posts directory (defaults to site/src/content/posts)",
    )
    parser.add_argument(
        "--public-dir",
        type=str,
        default=None,
        help="Override public directory (defaults to site/public)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent
    site_dir = repo_root / "site"
    posts_dir = Path(args.posts_dir) if args.posts_dir else (site_dir / "src" / "content" / "posts")
    public_dir = Path(args.public_dir) if args.public_dir else (site_dir / "public")

    if not posts_dir.exists():
        print(f"[error] Posts directory not found: {posts_dir}")
        return 2
    if not public_dir.exists():
        print(f"[error] Public directory not found: {public_dir}")
        return 2

    all_issues: List[ValidationIssue] = []
    for md_path in sorted(posts_dir.glob("*.md")):
        all_issues.extend(
            validate_post_frontmatter_contracts(
                md_path=md_path,
                public_dir=public_dir,
                fix=bool(args.fix),
            )
        )

    if all_issues:
        _print_issues(all_issues)
        errors = [i for i in all_issues if i.severity == "error"]
        warnings = [i for i in all_issues if i.severity == "warning"]
        print(f"\nValidation summary: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1 if errors else 0

    print("Content validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
