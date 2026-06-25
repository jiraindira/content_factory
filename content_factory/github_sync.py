"""
GitHub file sync — commits runtime-written files back to the repo
so they survive Railway redeploys.

Uses the GitHub Contents API (no git CLI needed).
Set GITHUB_TOKEN in Railway Variables. Falls back silently if not configured.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "jiraindira/content_factory").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()
REPO_ROOT     = Path(__file__).resolve().parents[1]


def _headers() -> dict:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "said-by-content-factory",
    }


def _api_url(rel_path: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{rel_path}"


def _get_sha(rel_path: str) -> str | None:
    """Return the current blob SHA of the file in the repo, or None if absent."""
    try:
        req = urllib.request.Request(
            f"{_api_url(rel_path)}?ref={GITHUB_BRANCH}",
            headers=_headers(),
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def sync_file(local_path: Path, message: str | None = None) -> bool:
    """
    Create or update a file in the GitHub repo from its local path.
    Safe to call from a FastAPI BackgroundTask — never raises.
    """
    if not GITHUB_TOKEN:
        return False
    try:
        rel_path = local_path.relative_to(REPO_ROOT).as_posix()
        content  = base64.b64encode(local_path.read_bytes()).decode()
        sha      = _get_sha(rel_path)

        body: dict = {
            "message": message or f"chore: sync {rel_path}",
            "content": content,
            "branch":  GITHUB_BRANCH,
        }
        if sha:
            body["sha"] = sha

        req = urllib.request.Request(
            _api_url(rel_path),
            data=json.dumps(body).encode(),
            headers=_headers(),
            method="PUT",
        )
        with urllib.request.urlopen(req) as resp:
            ok = resp.status in (200, 201)
            if ok:
                print(f"[github_sync] synced {rel_path}")
            return ok
    except Exception as e:
        print(f"[github_sync] warning: could not sync {local_path}: {e}")
        return False


def delete_file(local_path: Path, message: str | None = None) -> bool:
    """Delete a file from the GitHub repo. Safe to call from a BackgroundTask."""
    if not GITHUB_TOKEN:
        return False
    try:
        rel_path = local_path.relative_to(REPO_ROOT).as_posix()
        sha = _get_sha(rel_path)
        if not sha:
            return True  # already gone

        body = {
            "message": message or f"chore: delete {rel_path}",
            "sha":     sha,
            "branch":  GITHUB_BRANCH,
        }
        req = urllib.request.Request(
            _api_url(rel_path),
            data=json.dumps(body).encode(),
            headers=_headers(),
            method="DELETE",
        )
        with urllib.request.urlopen(req) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[github_sync] warning: could not delete {local_path}: {e}")
        return False
