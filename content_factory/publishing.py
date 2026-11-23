"""Optional publishing of approved articles to a client's own channels.

Email delivery stays the default. A brand opts in by adding a ``publishing``
list to its YAML profile::

    publishing:
      - id: blog                    # unique within the brand; keys the result
        type: wordpress             # github | wordpress | webhook
        mode: draft                 # draft (client presses publish) | publish (live)
        site_url: https://example.com
        username: jit
        secret_env: WP_APP_PASSWORD_JIT_PURU   # env var holding the app password
        slot_types: [long_blog]     # optional; default = every slot type
        enabled: true               # optional; default true

      - id: zapier
        type: webhook
        url_env: PUBLISH_WEBHOOK_JIT_PURU      # env var holding the hook URL
        secret_env: PUBLISH_WEBHOOK_SECRET     # optional; signs the body (HMAC-SHA256)

      - id: site
        type: github                # commits a markdown post to the client's repo
        repo: acme/acme-site
        branch: main                # optional; default main
        path: content/posts/{date}-{slug}.md   # optional; {date} {slug} {year} {month}
        token_env: GITHUB_TOKEN_ACME           # fine-grained token, Contents: write
        mode: draft                 # writes `draft: true` in the front matter
        post_url: https://acme.com/blog/{slug}/  # optional; link shown in admin

Secrets are only ever referenced by environment-variable *name*: brand YAMLs
are synced to GitHub, so passwords and hook URLs must never be written there.

Each attempt is recorded on the article YAML under ``publications.<id>``. A
destination that already succeeded is never sent the same article again.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
import yaml

TIMEOUT_SECONDS = 20.0
SUCCESS_STATUSES = {"draft", "published", "sent"}
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


class PublishError(Exception):
    """A destination rejected the article or is misconfigured."""


# ── Markdown → HTML ──────────────────────────────────────────────────────────

def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)
    return text


def markdown_to_html(md: str) -> str:
    """Convert the article markdown the writer produces into clean blog HTML.

    Handles headings, paragraphs, bullet/numbered lists, blockquotes, rules,
    bold, italic and links — everything ``article_writer`` emits.
    """
    out: list[str] = []
    para: list[str] = []
    list_tag: str | None = None
    list_items: list[str] = []
    quote: list[str] = []

    def flush() -> None:
        nonlocal list_tag
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()
        if list_tag:
            items = "".join(f"<li>{_inline(i)}</li>" for i in list_items)
            out.append(f"<{list_tag}>{items}</{list_tag}>")
            list_items.clear()
            list_tag = None
        if quote:
            out.append(f"<blockquote><p>{_inline(' '.join(quote))}</p></blockquote>")
            quote.clear()

    for raw in md.splitlines():
        line = raw.strip()
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        bullet = re.match(r"^[-*+]\s+(.*)$", line)
        numbered = re.match(r"^\d+[.)]\s+(.*)$", line)
        if not line:
            flush()
        elif heading:
            flush()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif re.match(r"^(-{3,}|\*{3,}|_{3,})$", line):
            flush()
            out.append("<hr/>")
        elif bullet or numbered:
            tag = "ul" if bullet else "ol"
            if list_tag != tag or para or quote:
                flush()
                list_tag = tag
            list_items.append((bullet or numbered).group(1))
        elif line.startswith(">"):
            if para or list_tag:
                flush()
            quote.append(line.lstrip("> ").strip())
        else:
            if list_tag or quote:
                flush()
            para.append(line)
    flush()
    return "\n".join(out)


def split_title(markdown: str, fallback: str = "") -> tuple[str, str]:
    """Return (title, body) — the leading ``# H1`` becomes the post title."""
    lines = markdown.lstrip().splitlines()
    if lines and re.match(r"^#\s+", lines[0]):
        return lines[0][1:].strip(), "\n".join(lines[1:]).strip()
    return " ".join(fallback.split()), markdown.strip()


# ── Config helpers ───────────────────────────────────────────────────────────

def destinations_for(brand: dict, slot_type: str | None = None) -> list[dict]:
    """Enabled destinations for a brand, optionally filtered by slot type."""
    dests = []
    for d in brand.get("publishing") or []:
        if not isinstance(d, dict) or d.get("enabled", True) is False:
            continue
        allowed = d.get("slot_types")
        if slot_type and allowed and slot_type not in allowed:
            continue
        dests.append(d)
    return dests


def _secret(dest: dict, key: str, *, required: bool = True) -> str:
    name = str(dest.get(key) or "").strip()
    if not name:
        if required:
            raise PublishError(f"'{key}' is not set for destination '{dest.get('id')}'")
        return ""
    if not _ENV_NAME.match(name):
        raise PublishError(f"'{key}' must be an environment variable name like WP_APP_PASSWORD_ACME")
    value = os.environ.get(name, "").strip()
    if not value and required:
        raise PublishError(f"environment variable {name} is not set")
    return value


def _mode(dest: dict) -> str:
    mode = str(dest.get("mode") or "draft").lower()
    if mode not in {"draft", "publish"}:
        raise PublishError(f"mode must be 'draft' or 'publish', got '{mode}'")
    return mode


_FIELDS = {
    "github": {"repo", "branch", "path", "token_env", "post_url"},
    "wordpress": {"site_url", "username", "secret_env"},
    "webhook": {"url_env", "secret_env"},
}
_ENV_KEYS = {"token_env", "secret_env", "url_env"}
_REQUIRED = {"github": {"repo", "token_env"}, "wordpress": {"site_url", "username", "secret_env"},
             "webhook": {"url_env"}}


def normalize_destinations(raw: Any) -> list[dict]:
    """Validate and clean a ``publishing`` list submitted from the admin form.

    Raises ValueError with an operator-readable message. Keeps only known
    fields, so a pasted token can't sneak into the (GitHub-synced) brand YAML
    through an unexpected key.
    """
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError("publishing must be a list of destinations")
    out, seen = [], set()
    for i, d in enumerate(raw, 1):
        if not isinstance(d, dict):
            raise ValueError(f"destination {i} is not an object")
        kind = str(d.get("type") or "").strip()
        if kind not in _FIELDS:
            raise ValueError(f"destination {i}: type must be one of {', '.join(sorted(_FIELDS))}")
        dest_id = slugify(str(d.get("id") or kind), 40)
        if dest_id in seen:
            raise ValueError(f"destination {i}: name '{dest_id}' is used twice")
        seen.add(dest_id)
        mode = str(d.get("mode") or "draft").lower()
        if mode not in {"draft", "publish"}:
            raise ValueError(f"{dest_id}: mode must be draft or publish")
        clean: dict[str, Any] = {"id": dest_id, "type": kind, "enabled": d.get("enabled", True) is not False,
                                 "mode": mode}
        for key in sorted(_FIELDS[kind]):
            val = str(d.get(key) or "").strip()
            if not val:
                continue
            if key in _ENV_KEYS and not _ENV_NAME.match(val):
                raise ValueError(
                    f"{dest_id}: {key} must be the NAME of a Railway variable (like GITHUB_TOKEN_ACME), "
                    "not the secret itself"
                )
            if key in {"site_url", "post_url"} and not val.startswith("https://"):
                raise ValueError(f"{dest_id}: {key} must start with https://")
            if key == "repo" and not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", val):
                raise ValueError(f"{dest_id}: repo must look like owner/name")
            clean[key] = val
        missing = _REQUIRED[kind] - clean.keys()
        if missing:
            raise ValueError(f"{dest_id}: missing {', '.join(sorted(missing))}")
        slot_types = d.get("slot_types")
        if slot_types:
            clean["slot_types"] = [str(t) for t in slot_types if t in ("long_blog", "short_snippet")]
        out.append(clean)
    return out


def env_status(dests: list[dict]) -> dict[str, bool]:
    """Which referenced environment variables are actually set (never their values)."""
    names = {str(d.get(k)) for d in dests for k in _ENV_KEYS if d.get(k)}
    return {n: bool(os.environ.get(n, "").strip()) for n in sorted(names)}


# ── Destinations ─────────────────────────────────────────────────────────────

def publish_wordpress(*, dest: dict, title: str, body_html: str, client: httpx.Client) -> dict:
    site = str(dest.get("site_url") or "").rstrip("/")
    user = str(dest.get("username") or "")
    if not site.startswith("https://"):
        raise PublishError("site_url must be an https:// address")
    if not user:
        raise PublishError("username is not set")
    password = _secret(dest, "secret_env")
    mode = _mode(dest)

    resp = client.post(
        f"{site}/wp-json/wp/v2/posts",
        auth=(user, password),
        json={"title": title, "content": body_html, "status": mode},
    )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("message") or resp.text
        except ValueError:
            detail = resp.text
        raise PublishError(f"WordPress returned {resp.status_code}: {str(detail)[:200]}")
    post = resp.json()
    return {
        "status": "published" if mode == "publish" else "draft",
        "remote_id": post.get("id"),
        "url": post.get("link") or "",
    }


def slugify(text: str, max_len: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().replace("'", "").replace("\u2019", "")).strip("-")
    return slug[:max_len].rstrip("-") or "post"


def _excerpt(body_md: str, limit: int = 160) -> str:
    for block in body_md.split("\n\n"):
        b = block.strip()
        if b and not b.startswith(("#", "-", "*", ">", "|")) and not re.match(r"^\d+[.)]\s", b):
            plain = re.sub(r"[*_`]|\[([^\]]+)\]\([^)]+\)", lambda m: m.group(1) or "", " ".join(b.split()))
            return plain if len(plain) <= limit else plain[: limit - 1].rsplit(" ", 1)[0] + "\u2026"
    return ""


def build_markdown_post(*, title: str, body_md: str, date: str, slug: str, draft: bool, author: str = "") -> str:
    """A markdown file with YAML front matter that Hugo, Jekyll, Astro, Eleventy
    and Next.js content folders all understand."""
    front = {"title": title, "date": date, "slug": slug, "draft": draft}
    if author:
        front["author"] = author
    desc = _excerpt(body_md)
    if desc:
        front["description"] = desc
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm}\n---\n\n{body_md.strip()}\n"


def publish_github(*, dest: dict, title: str, body_md: str, date: str, author: str,
                   client: httpx.Client) -> dict:
    repo = str(dest.get("repo") or "").strip()
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo):
        raise PublishError("repo must look like owner/name")
    branch = str(dest.get("branch") or "main")
    token = _secret(dest, "token_env")
    mode = _mode(dest)

    slug = slugify(title)
    year, month = (date.split("-") + ["", ""])[:2]
    fields = {"date": date, "slug": slug, "year": year, "month": month}
    template = str(dest.get("path") or "content/posts/{date}-{slug}.md")
    try:
        path = template.format(**fields).lstrip("/")
    except (KeyError, IndexError) as e:
        raise PublishError(f"path template uses an unknown field: {e}")
    if ".." in path.split("/"):
        raise PublishError("path may not contain '..'")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "said-by-content-factory",
    }
    api = f"https://api.github.com/repos/{repo}/contents/{path}"

    existing = client.get(api, params={"ref": branch}, headers=headers)
    if existing.status_code == 200:
        raise PublishError(f"{path} already exists in {repo}; not overwriting the client's file")
    if existing.status_code not in (404,):
        raise PublishError(f"GitHub returned {existing.status_code} checking {path}: {existing.text[:200]}")

    content = build_markdown_post(title=title, body_md=body_md, date=date, slug=slug,
                                  draft=(mode == "draft"), author=author)
    resp = client.put(api, headers=headers, json={
        "message": f"Add post: {title}",
        "content": base64.b64encode(content.encode("utf-8")).decode(),
        "branch": branch,
    })
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("message") or resp.text
        except ValueError:
            detail = resp.text
        raise PublishError(f"GitHub returned {resp.status_code}: {str(detail)[:200]}")
    data = resp.json()
    post_url = str(dest.get("post_url") or "")
    url = post_url.format(**fields) if post_url else (data.get("content") or {}).get("html_url", "")
    return {
        "status": "published" if mode == "publish" else "draft",
        "remote_id": (data.get("commit") or {}).get("sha", ""),
        "path": path,
        "url": url,
    }


def publish_webhook(*, dest: dict, payload: dict, client: httpx.Client) -> dict:
    url = _secret(dest, "url_env")
    if not url.startswith("https://"):
        raise PublishError("webhook URL must be an https:// address")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    signing_key = _secret(dest, "secret_env", required=False)
    if signing_key:
        sig = hmac.new(signing_key.encode(), body, hashlib.sha256).hexdigest()
        headers["X-SaidBy-Signature"] = f"sha256={sig}"

    resp = client.post(url, content=body, headers=headers)
    if resp.status_code >= 400:
        raise PublishError(f"webhook returned {resp.status_code}: {resp.text[:200]}")
    result: dict[str, Any] = {"status": "sent", "url": ""}
    try:
        data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("url"), str):
            result["url"] = data["url"]
    except ValueError:
        pass
    return result


# ── Orchestration ────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def publish_article(
    *,
    brand: dict,
    article: dict,
    run_id: str,
    client_factory: Callable[[], httpx.Client] | None = None,
) -> dict:
    """Send an approved article to each of the brand's enabled destinations.

    Updates ``article["publications"]`` in place and returns it. Never raises
    for a destination failure: the error is recorded instead, so a broken
    integration can't block the email delivery that already happened.
    """
    pubs: dict = article.setdefault("publications", {}) or {}
    article["publications"] = pubs
    dests = destinations_for(brand, article.get("slot_type"))
    if not dests:
        return pubs

    title, body_md = split_title(article.get("content", ""), article.get("topic", ""))
    body_html = markdown_to_html(body_md)
    factory = client_factory or (lambda: httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True))

    with factory() as client:
        for dest in dests:
            dest_id = str(dest.get("id") or dest.get("type") or "destination")
            prior = pubs.get(dest_id) or {}
            if prior.get("status") in SUCCESS_STATUSES:
                continue  # already delivered — never post twice
            kind = dest.get("type")
            try:
                if kind == "github":
                    result = publish_github(
                        dest=dest, title=title, body_md=body_md,
                        date=str(article.get("generated_at") or _now()[:10]),
                        author=str(brand.get("client_name") or ""), client=client,
                    )
                elif kind == "wordpress":
                    result = publish_wordpress(dest=dest, title=title, body_html=body_html, client=client)
                elif kind == "webhook":
                    payload = {
                        "event": "article.approved",
                        "brand_id": brand.get("brand_id"),
                        "client_name": brand.get("client_name"),
                        "run_id": run_id,
                        "title": title,
                        "slot_type": article.get("slot_type"),
                        "generated_at": str(article.get("generated_at") or ""),
                        "mode": _mode(dest),
                        "markdown": body_md,
                        "html": body_html,
                    }
                    result = publish_webhook(dest=dest, payload=payload, client=client)
                else:
                    raise PublishError(f"unknown destination type '{kind}'")
                result.update({"type": kind, "at": _now(), "attempts": int(prior.get("attempts", 0)) + 1})
                pubs[dest_id] = result
            except (PublishError, httpx.HTTPError) as e:
                msg = str(e) if isinstance(e, PublishError) else f"could not reach {kind}: {type(e).__name__}"
                pubs[dest_id] = {
                    "type": kind, "status": "failed", "error": msg, "at": _now(),
                    "attempts": int(prior.get("attempts", 0)) + 1,
                }
                print(f"[publish] {brand.get('brand_id')}/{run_id} → {dest_id} failed: {msg}")
    return pubs


def summarize(pubs: dict) -> dict:
    failed = [k for k, v in (pubs or {}).items() if v.get("status") == "failed"]
    ok = [k for k, v in (pubs or {}).items() if v.get("status") in SUCCESS_STATUSES]
    return {"published": ok, "failed": failed}
