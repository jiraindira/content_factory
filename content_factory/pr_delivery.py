from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from managed_site.hydration import hydrate_blog_post_from_package


@dataclass(frozen=True)
class PrDeliveryResult:
    managed_repo_path: Path
    branch_name: str
    changed_files: int
    post_path: Path


def _run_git(args: list[str], *, cwd: Path) -> str:
    p = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        msg = (p.stderr or p.stdout or "").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {msg}")
    return (p.stdout or "").strip()


def _sanitize_branch_component(s: str) -> str:
    s2 = re.sub(r"[^a-zA-Z0-9._/-]+", "-", (s or "").strip())
    s2 = re.sub(r"-+", "-", s2).strip("-/")
    return s2 or "delivery"


def default_branch_name(*, brand_id: str, run_id: str) -> str:
    return f"content/{_sanitize_branch_component(brand_id)}/{_sanitize_branch_component(run_id)}"


def ensure_managed_repo_checkout(
    *,
    checkout_path: Path,
    managed_repo_url: str | None,
) -> Path:
    checkout_path.parent.mkdir(parents=True, exist_ok=True)

    if checkout_path.exists() and (checkout_path / ".git").exists():
        return checkout_path

    if checkout_path.exists() and not (checkout_path / ".git").exists():
        raise FileExistsError(f"Checkout path exists but is not a git repo: {checkout_path}")

    if not managed_repo_url:
        raise ValueError("managed_repo_url is required when checkout_path does not exist")

    _run_git(["clone", managed_repo_url, str(checkout_path)], cwd=checkout_path.parent)
    return checkout_path


def deliver_package_as_pr(
    *,
    package_dir: Path,
    managed_repo_path: Path,
    base_branch: str = "main",
    branch_name: str | None = None,
    overwrite: bool = True,
    enrich_pick_images: bool = True,
    regen_hero_if_possible: bool = False,
    commit: bool = False,
    push: bool = False,
) -> PrDeliveryResult:
    if not managed_repo_path.exists() or not (managed_repo_path / ".git").exists():
        raise FileNotFoundError(f"managed_repo_path is not a git repo: {managed_repo_path}")

    if branch_name is None:
        # Derive from package directory name; good enough for now.
        branch_name = default_branch_name(brand_id=package_dir.parent.name, run_id=package_dir.name)

    _run_git(["fetch", "origin"], cwd=managed_repo_path)
    _run_git(["checkout", base_branch], cwd=managed_repo_path)
    _run_git(["pull", "--ff-only", "origin", base_branch], cwd=managed_repo_path)
    _run_git(["checkout", "-B", branch_name], cwd=managed_repo_path)

    res = hydrate_blog_post_from_package(
        repo_root=managed_repo_path,
        package_dir=package_dir,
        overwrite=overwrite,
        enrich_pick_images=enrich_pick_images,
        dry_run=False,
        regen_hero_if_possible=regen_hero_if_possible,
    )

    status = _run_git(["status", "--porcelain"], cwd=managed_repo_path)
    changed_lines = [ln for ln in status.splitlines() if ln.strip()]

    if changed_lines:
        _run_git(["add", "-A"], cwd=managed_repo_path)

    if commit:
        if not changed_lines:
            # No-op; avoid creating empty commits.
            pass
        else:
            msg = f"Hydrate content package: {res.post_slug}"
            _run_git(["commit", "-m", msg], cwd=managed_repo_path)

    if push:
        if not commit:
            raise ValueError("push=True requires commit=True")
        _run_git(["push", "-u", "origin", branch_name], cwd=managed_repo_path)

    return PrDeliveryResult(
        managed_repo_path=managed_repo_path,
        branch_name=branch_name,
        changed_files=len(changed_lines),
        post_path=res.post_path,
    )


def has_gh_cli() -> bool:
    return shutil.which("gh") is not None
