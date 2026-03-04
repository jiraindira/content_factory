from __future__ import annotations

import shutil
import traceback
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class HeroPaths:
    """
    Canonical hero asset paths relative to `site/public`.
    We keep these deterministic so self-heal can recreate them exactly.
    """
    hero: str
    hero_home: str
    hero_card: str
    hero_source: str

    @staticmethod
    def for_slug(slug: str) -> "HeroPaths":
        base = f"/images/posts/{slug}"
        return HeroPaths(
            hero=f"{base}/hero.webp",
            hero_home=f"{base}/hero_home.webp",
            hero_card=f"{base}/hero_card.webp",
            hero_source=f"{base}/hero_source.webp",
        )


def _disk_path(public_dir: Path, url_path: str) -> Path:
    # url_path is like /images/posts/.../hero.webp
    return public_dir / url_path.lstrip("/")


def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def _missing_or_empty(p: Path) -> bool:
    return (not p.exists()) or p.stat().st_size == 0


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_same_file(a: Path, b: Path) -> bool:
    if (not a.exists()) or (not b.exists()):
        return False
    if a.stat().st_size != b.stat().st_size:
        return False
    return _sha256(a) == _sha256(b)


def ensure_hero_assets_exist(
    *,
    public_dir: Path,
    slug: str,
    placeholder_url: str = "/images/placeholder-hero.webp",
    regen_fn=None,
    regen_kwargs: Optional[dict] = None,
) -> HeroPaths:
    """
    Self-heal hero assets for a slug.

    Strategy:
    - If all expected hero files exist and are non-empty: do nothing.
    - Else, if regen_fn is provided: attempt regeneration.
    - If regen fails OR regen_fn not provided: copy placeholder into ALL expected paths.

    regen_fn should be something like:
        regen_fn(**regen_kwargs) -> object with attributes:
            hero_image_path, hero_image_home_path, hero_image_card_path, hero_source_path (optional)
    """
    paths = HeroPaths.for_slug(slug)

    placeholder_disk = _disk_path(public_dir, placeholder_url)
    if not placeholder_disk.exists():
        raise FileNotFoundError(
            f"Placeholder hero missing at {placeholder_disk}. "
            f"Create it (e.g. site/public/images/placeholder-hero.webp) so self-heal can backfill."
        )

    expected = [
        _disk_path(public_dir, paths.hero),
        _disk_path(public_dir, paths.hero_home),
        _disk_path(public_dir, paths.hero_card),
        _disk_path(public_dir, paths.hero_source),
    ]

    def _missing_or_placeholder(p: Path) -> bool:
        return _missing_or_empty(p) or _is_same_file(p, placeholder_disk)

    if all(not _missing_or_placeholder(p) for p in expected):
        return paths

    # Try regeneration first (if provided)
    if regen_fn is not None:
        try:
            regen_kwargs = regen_kwargs or {}

            # If placeholder files are present, remove them so the image agent won't treat
            # them as "already generated" and skip regeneration.
            for p in expected:
                try:
                    if _is_same_file(p, placeholder_disk):
                        p.unlink(missing_ok=True)
                except Exception:
                    pass

            hero_obj = regen_fn(**regen_kwargs)

            # If regen succeeded, ensure the canonical files exist.
            # Some pipelines may only generate `hero.webp`. If so, we still backfill others via placeholder.
            expected_after = expected
            for p in expected_after:
                if _missing_or_placeholder(p):
                    # Regen did not create all expected assets.
                    # We'll fall through and backfill missing ones with placeholder.
                    print(
                        f"🟠 Hero regen incomplete for slug '{slug}'; will backfill missing assets with placeholder."
                    )
                    break
            else:
                return paths
        except Exception as e:
            # fall through to placeholder backfill
            print(f"🟠 Hero regen failed for slug '{slug}'; using placeholder. Error: {e}")
            print(traceback.format_exc())
            pass

    for p in expected:
        if _missing_or_placeholder(p):
            _ensure_parent(p)
            shutil.copyfile(placeholder_disk, p)

    return paths
