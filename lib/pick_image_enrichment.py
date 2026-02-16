from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml


RE_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
RE_PRODUCTS_LINE_JSON = re.compile(r"^products:\s*(\[.*\])\s*$", re.MULTILINE)


@dataclass(frozen=True)
class PickImageEnrichmentResult:
    updated: bool
    picks_updated: int
    picks_skipped: int
    errors: list[str]


class _MetaTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        d: dict[str, str] = {}
        for k, v in attrs:
            if k is None or v is None:
                continue
            d[k.lower()] = v
        if d:
            self.meta.append(d)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _extract_frontmatter(md: str) -> str | None:
    m = RE_FRONTMATTER.search(md)
    return m.group(1) if m else None


def _resolve_url(base: str, maybe_relative: str) -> str:
    if maybe_relative.startswith("//"):
        parsed = urlparse(base)
        return f"{parsed.scheme}:{maybe_relative}"
    if maybe_relative.startswith("/"):
        parsed = urlparse(base)
        return f"{parsed.scheme}://{parsed.netloc}{maybe_relative}"
    return maybe_relative


def _extract_og_image(html: str) -> str | None:
    parser = _MetaTagParser()
    try:
        parser.feed(html)
    except Exception:
        return None

    for tag in parser.meta:
        if tag.get("property") == "og:image" and tag.get("content"):
            return tag["content"].strip()
    for tag in parser.meta:
        if tag.get("name") == "twitter:image" and tag.get("content"):
            return tag["content"].strip()
    for tag in parser.meta:
        if tag.get("property") == "og:image:secure_url" and tag.get("content"):
            return tag["content"].strip()
    return None


def _looks_like_amazon(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host.endswith(
        (
            "amazon.com",
            "amazon.co.uk",
            "amazon.de",
            "amazon.fr",
            "amazon.it",
            "amazon.es",
            "amazon.ca",
            "amazon.co.jp",
            "amazon.in",
        )
    )


def _extract_amazon_product_image(html: str) -> str | None:
    m = re.search(r'id="landingImage"[^>]*?data-old-hires="([^"]+)"', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    m = re.search(r'id="landingImage"[^>]*?data-a-dynamic-image="([^"]+)"', html, re.IGNORECASE)
    if m:
        raw = m.group(1)
        raw = raw.replace("&quot;", '"')
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                for k in data.keys():
                    if isinstance(k, str) and k.startswith("http"):
                        return k.strip()
        except Exception:
            pass

    for key in ("hiRes", "large"):
        m = re.search(rf'"{key}"\s*:\s*"(https:[^"]+)"', html)
        if m:
            return m.group(1).strip()

    return None


def _is_probably_placeholder_image(image_url: str) -> bool:
    u = image_url.lower().strip()
    if "amazon" in u and ("logo" in u or "nav" in u or "sprite" in u):
        return True
    return False


def _ext_from_content_type(ct: str | None) -> str | None:
    if not ct:
        return None
    ct = ct.split(";")[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(ct)


def _download_image(*, client: httpx.Client, url: str, out_path: Path) -> bool:
    try:
        r = client.get(url, timeout=20.0)
        r.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(r.content)
        return True
    except Exception:
        return False


def _fetch_best_image_url(*, client: httpx.Client, product_url: str) -> str | None:
    try:
        r = client.get(product_url, timeout=20.0)
        r.raise_for_status()
        html = r.text
    except Exception:
        return None

    base_url = str(getattr(r, "url", product_url))

    img = _extract_og_image(html)
    if img:
        img = _resolve_url(base_url, img)
        if not _is_probably_placeholder_image(img):
            return img

    # Amazon pages often omit OG tags or vary markup.
    if _looks_like_amazon(base_url):
        img2 = _extract_amazon_product_image(html)
        if img2:
            img2 = _resolve_url(base_url, img2)
            if not _is_probably_placeholder_image(img2):
                return img2

    return None


def _extract_products_json_line(frontmatter: str) -> tuple[list[dict[str, Any]], str] | None:
    m = RE_PRODUCTS_LINE_JSON.search(frontmatter)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        products = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(products, list):
        return None
    normalized: list[dict[str, Any]] = []
    for item in products:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized, raw


def enrich_pick_images_for_markdown(
    *,
    markdown_path: Path,
    slug: str,
    repo_root: Path | None = None,
    allow_yaml_frontmatter_rewrite: bool = False,
    dry_run: bool = False,
    max_picks: int = 0,
    force: bool = False,
) -> PickImageEnrichmentResult:
    """Populate products[].image and download images under site/public.

    Supports the repo’s preferred Astro post format where `products:` is a single-line JSON array.
    If `allow_yaml_frontmatter_rewrite=True`, will also handle YAML-list products by rewriting the
    whole frontmatter block (used for content_factory outputs).
    """

    errors: list[str] = []
    picks_updated = 0
    picks_skipped = 0

    repo = repo_root or Path(__file__).resolve().parents[1]
    public_picks_dir = repo / "site" / "public" / "images" / "picks" / slug

    md = _read_text(markdown_path)
    fm = _extract_frontmatter(md)
    if not fm:
        return PickImageEnrichmentResult(updated=False, picks_updated=0, picks_skipped=0, errors=["missing frontmatter"])

    products: list[dict[str, Any]] | None = None
    raw_products_json: str | None = None
    use_json_line = False

    extracted = _extract_products_json_line(fm)
    if extracted:
        products, raw_products_json = extracted
        use_json_line = True
    elif allow_yaml_frontmatter_rewrite:
        try:
            fm_data = yaml.safe_load(fm) or {}
            prod_val = fm_data.get("products")
            if isinstance(prod_val, list):
                products = [p for p in prod_val if isinstance(p, dict)]
        except Exception:
            products = None

    if not products:
        return PickImageEnrichmentResult(updated=False, picks_updated=0, picks_skipped=0, errors=["no products found"])

    headers = {
        # Use a mainstream UA; some retailers serve interstitial pages otherwise.
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-GB,en;q=0.9",
    }

    updated_any = False
    with httpx.Client(follow_redirects=True, headers=headers) as client:
        for i, p in enumerate(products):
            if max_picks and i >= max_picks:
                break

            pick_id = str(p.get("pick_id") or "").strip()
            url = str(p.get("url") or "").strip()
            if not pick_id or not url:
                picks_skipped += 1
                continue

            existing = str(p.get("image") or "").strip()

            old_local_abs: Path | None = None
            if force and existing.startswith("/images/picks/"):
                old_local_abs = repo / "site" / "public" / existing.lstrip("/")

            # If already set and file exists, skip.
            if (not force) and existing and existing.startswith(f"/images/picks/{slug}/"):
                existing_file = repo / "site" / "public" / existing.lstrip("/")
                if existing_file.exists():
                    picks_skipped += 1
                    continue

            image_url = _fetch_best_image_url(client=client, product_url=url)
            if not image_url:
                errors.append(f"no og image for {pick_id}")
                picks_skipped += 1
                continue

            # Determine extension
            ext = None
            try:
                head = client.head(image_url, timeout=20.0)
                ext = _ext_from_content_type(head.headers.get("content-type"))
            except Exception:
                ext = None
            if not ext:
                # Fallback to jpg
                ext = ".jpg"

            out_file = public_picks_dir / f"{pick_id}{ext}"
            if dry_run:
                p["image"] = f"/images/picks/{slug}/{out_file.name}"
                updated_any = True
                picks_updated += 1
                continue

            if not _download_image(client=client, url=image_url, out_path=out_file):
                errors.append(f"download failed for {pick_id}")
                picks_skipped += 1
                continue

            p["image"] = f"/images/picks/{slug}/{out_file.name}"
            updated_any = True
            picks_updated += 1

            if force and old_local_abs and old_local_abs.exists():
                try:
                    if old_local_abs.resolve() != out_file.resolve():
                        old_local_abs.unlink(missing_ok=True)
                except Exception:
                    pass

    if not updated_any:
        return PickImageEnrichmentResult(updated=False, picks_updated=picks_updated, picks_skipped=picks_skipped, errors=errors)

    if dry_run:
        return PickImageEnrichmentResult(updated=True, picks_updated=picks_updated, picks_skipped=picks_skipped, errors=errors)

    if use_json_line and raw_products_json is not None:
        new_json = json.dumps(products, ensure_ascii=False)
        new_fm = RE_PRODUCTS_LINE_JSON.sub(f"products: {new_json}", fm)
        new_md = md.replace(f"---\n{fm}\n---", f"---\n{new_fm}\n---", 1)
        _write_text(markdown_path, new_md)
        return PickImageEnrichmentResult(updated=True, picks_updated=picks_updated, picks_skipped=picks_skipped, errors=errors)

    if allow_yaml_frontmatter_rewrite:
        try:
            fm_data2 = yaml.safe_load(fm) or {}
            fm_data2["products"] = products
            new_fm = yaml.safe_dump(fm_data2, sort_keys=False).strip()
            new_md = md.replace(f"---\n{fm}\n---", f"---\n{new_fm}\n---", 1)
            _write_text(markdown_path, new_md)
            return PickImageEnrichmentResult(updated=True, picks_updated=picks_updated, picks_skipped=picks_skipped, errors=errors)
        except Exception as e:
            errors.append(f"yaml rewrite failed: {e}")
            return PickImageEnrichmentResult(updated=False, picks_updated=picks_updated, picks_skipped=picks_skipped, errors=errors)

    return PickImageEnrichmentResult(updated=False, picks_updated=picks_updated, picks_skipped=picks_skipped, errors=errors)
