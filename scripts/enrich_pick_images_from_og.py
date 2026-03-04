"""Populate products[].image for Astro posts by scraping og:image.

This wraps the shared implementation in lib.pick_image_enrichment so all pipelines
use one codepath.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Allow running as a plain script (python scripts/...) without installing as a package.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib.pick_image_enrichment import enrich_pick_images_for_markdown  # noqa: E402


RE_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
RE_PUBLISHED_AT = re.compile(r"^publishedAt:\s*([\"']?)([^\n\"']+)(\1)\s*$", re.MULTILINE)
RE_FEATURED = re.compile(r"^featured:\s*(true|false)\s*$", re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class PostRef:
    slug: str
    path: Path
    published_at: datetime
    featured: bool


def _parse_iso8601(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_frontmatter(md: str) -> str | None:
    m = RE_FRONTMATTER.search(md)
    return m.group(1) if m else None


def _find_published_at(frontmatter: str) -> datetime | None:
    m = RE_PUBLISHED_AT.search(frontmatter)
    if not m:
        return None
    return _parse_iso8601(m.group(2))


def _find_featured(frontmatter: str) -> bool:
    m = RE_FEATURED.search(frontmatter)
    if not m:
        return False
    return m.group(1).lower() == "true"


def _list_posts(posts_dir: Path) -> list[PostRef]:
    posts: list[PostRef] = []
    for path in posts_dir.glob("*.md"):
        slug = path.stem
        md = _read_text(path)
        fm = _extract_frontmatter(md)
        if not fm:
            continue
        published_at = _find_published_at(fm)
        if not published_at:
            continue
        featured = _find_featured(fm)
        posts.append(PostRef(slug=slug, path=path, published_at=published_at, featured=featured))

    posts.sort(key=lambda p: p.published_at, reverse=True)
    return posts


def _select_top_posts(all_posts: list[PostRef], top_posts: int, slug: str | None) -> list[PostRef]:
    if slug:
        for p in all_posts:
            if p.slug == slug:
                return [p]
        raise SystemExit(f"Slug not found: {slug}")

    featured = [p for p in all_posts if p.featured]
    seen = {p.slug for p in featured}
    recent = [p for p in all_posts if p.slug not in seen][:top_posts]
    return featured + recent


def _select_posts(all_posts: list[PostRef], *, slug: str | None, all_posts_flag: bool, top_posts: int) -> list[PostRef]:
    if slug:
        for p in all_posts:
            if p.slug == slug:
                return [p]
        raise SystemExit(f"Slug not found: {slug}")

    if all_posts_flag:
        return all_posts

    return _select_top_posts(all_posts, top_posts, slug=None)


def _safe_filename(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "pick"


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    posts_dir = repo_root / "site" / "src" / "content" / "posts"
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--all-posts",
        action="store_true",
        help="Process all posts under site/src/content/posts (only those with products will be updated).",
    )
    ap.add_argument(
        "--top-posts",
        type=int,
        default=12,
        help="Number of most recent posts to process (featured posts are always included). Ignored if --all-posts is set.",
    )
    ap.add_argument("--slug", type=str, default=None, help="Process only a single post slug (filename without .md).")
    ap.add_argument("--dry-run", action="store_true", help="Don’t write files; just report what would change.")
    ap.add_argument("--max-picks", type=int, default=0, help="Optional cap on picks per post (0 = no cap).")
    ap.add_argument("--force", action="store_true", help="Overwrite existing products[].image values and re-download thumbnails.")
    args = ap.parse_args(argv)

    if not posts_dir.exists():
        raise SystemExit(f"Posts directory not found: {posts_dir}")

    all_posts = _list_posts(posts_dir)
    selected = _select_posts(all_posts, slug=args.slug, all_posts_flag=bool(args.all_posts), top_posts=args.top_posts)

    if not selected:
        print("No posts selected.")
        return 0

    updated_posts = 0
    updated_picks = 0
    skipped_picks = 0

    for post in selected:
        res = enrich_pick_images_for_markdown(
            markdown_path=post.path,
            slug=post.slug,
            repo_root=repo_root,
            dry_run=bool(args.dry_run),
            max_picks=int(args.max_picks or 0),
            force=bool(args.force),
        )

        updated_picks += int(res.picks_updated)
        skipped_picks += int(res.picks_skipped)

        if res.updated:
            updated_posts += 1
            print(f"[ok] {post.slug}: updated")
        else:
            # Keep the output quiet unless the post was selected but not updatable.
            # This matches the previous script behavior which only printed on update.
            pass

    print(f"Posts updated: {updated_posts}")
    print(f"Picks updated: {updated_picks}")
    print(f"Picks skipped: {skipped_picks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
