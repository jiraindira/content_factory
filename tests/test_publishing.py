"""Optional publishing of approved articles to WordPress / webhooks."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

import onboarding_app
from content_factory import emailer, publishing

ARTICLE_MD = "# My Title\n\n## Section\n\nHello **bold** and *it*.\n\n- one\n- two\n\n> a quote\n\n1. first\n2. second\n"


def _article(**extra):
    return {"topic": "My Title", "slot_type": "long_blog", "generated_at": "2026-11-23",
            "status": "approved", "content": ARTICLE_MD, **extra}


def _factory(handler, calls):
    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)
    return lambda: httpx.Client(transport=httpx.MockTransport(wrapped))


WP = {"id": "blog", "type": "wordpress", "site_url": "https://blog.example.com", "username": "ada",
      "secret_env": "WP_TEST_PASSWORD"}


# ── markdown ────────────────────────────────────────────────────────────────

def test_markdown_to_html_covers_writer_output():
    title, body = publishing.split_title(ARTICLE_MD)
    assert title == "My Title"
    out = publishing.markdown_to_html(body)
    assert "<h1>" not in out
    assert "<h2>Section</h2>" in out
    assert "<p>Hello <strong>bold</strong> and <em>it</em>.</p>" in out
    assert "<ul><li>one</li><li>two</li></ul>" in out
    assert "<ol><li>first</li><li>second</li></ol>" in out
    assert "<blockquote><p>a quote</p></blockquote>" in out


def test_markdown_escapes_html():
    assert "&lt;script&gt;" in publishing.markdown_to_html("<script>x</script>")


# ── WordPress ───────────────────────────────────────────────────────────────

def test_wordpress_creates_draft_by_default(monkeypatch):
    monkeypatch.setenv("WP_TEST_PASSWORD", "abcd efgh")
    calls = []
    f = _factory(lambda r: httpx.Response(201, json={"id": 42, "link": "https://blog.example.com/?p=42"}), calls)
    article = _article()
    pubs = publishing.publish_article(brand={"brand_id": "ada", "publishing": [WP]}, article=article,
                                      run_id="r1", client_factory=f)
    assert pubs["blog"]["status"] == "draft" and pubs["blog"]["remote_id"] == 42
    assert pubs["blog"]["url"] == "https://blog.example.com/?p=42"
    req = calls[0]
    assert str(req.url) == "https://blog.example.com/wp-json/wp/v2/posts"
    assert req.headers["authorization"].startswith("Basic ")
    body = json.loads(req.content)
    assert body["status"] == "draft" and body["title"] == "My Title"
    assert "<h2>Section</h2>" in body["content"]


def test_success_is_never_posted_twice(monkeypatch):
    monkeypatch.setenv("WP_TEST_PASSWORD", "x")
    calls = []
    f = _factory(lambda r: httpx.Response(201, json={"id": 1, "link": "https://b/1"}), calls)
    brand = {"publishing": [{**WP, "mode": "publish"}]}
    article = _article()
    publishing.publish_article(brand=brand, article=article, run_id="r", client_factory=f)
    publishing.publish_article(brand=brand, article=article, run_id="r", client_factory=f)
    assert len(calls) == 1
    assert article["publications"]["blog"]["status"] == "published"


def test_failures_are_recorded_not_raised(monkeypatch):
    monkeypatch.setenv("WP_TEST_PASSWORD", "x")
    calls = []
    f = _factory(lambda r: httpx.Response(401, json={"message": "Bad password"}), calls)
    article = _article()
    pubs = publishing.publish_article(brand={"publishing": [WP]}, article=article, run_id="r", client_factory=f)
    assert pubs["blog"]["status"] == "failed" and "Bad password" in pubs["blog"]["error"]
    assert pubs["blog"]["attempts"] == 1


def test_missing_secret_fails_without_calling_out(monkeypatch):
    monkeypatch.delenv("WP_TEST_PASSWORD", raising=False)
    calls = []
    f = _factory(lambda r: httpx.Response(201, json={}), calls)
    pubs = publishing.publish_article(brand={"publishing": [WP]}, article=_article(), run_id="r", client_factory=f)
    assert calls == []
    assert "WP_TEST_PASSWORD is not set" in pubs["blog"]["error"]


def test_secret_must_be_an_env_name_not_a_value(monkeypatch):
    calls = []
    f = _factory(lambda r: httpx.Response(201, json={}), calls)
    bad = {**WP, "secret_env": "my actual password"}
    pubs = publishing.publish_article(brand={"publishing": [bad]}, article=_article(), run_id="r", client_factory=f)
    assert calls == [] and pubs["blog"]["status"] == "failed"


def test_disabled_and_filtered_destinations_are_skipped():
    brand = {"publishing": [{**WP, "enabled": False}, {**WP, "id": "x", "slot_types": ["short_snippet"]}]}
    assert publishing.destinations_for(brand, "long_blog") == []
    assert publishing.publish_article(brand=brand, article=_article(), run_id="r") == {}


# ── Webhook ─────────────────────────────────────────────────────────────────

def test_webhook_signs_body(monkeypatch):
    monkeypatch.setenv("HOOK_URL", "https://hooks.example.com/abc")
    monkeypatch.setenv("HOOK_SECRET", "s3cret")
    calls = []
    f = _factory(lambda r: httpx.Response(200, json={"url": "https://site/post"}), calls)
    dest = {"id": "zap", "type": "webhook", "url_env": "HOOK_URL", "secret_env": "HOOK_SECRET"}
    pubs = publishing.publish_article(brand={"brand_id": "ada", "publishing": [dest]}, article=_article(),
                                      run_id="r9", client_factory=f)
    assert pubs["zap"] == {**pubs["zap"], "status": "sent", "url": "https://site/post"}
    req = calls[0]
    expected = hmac.new(b"s3cret", req.content, hashlib.sha256).hexdigest()
    assert req.headers["x-saidby-signature"] == f"sha256={expected}"
    payload = json.loads(req.content)
    assert payload["run_id"] == "r9" and payload["title"] == "My Title" and payload["mode"] == "draft"


# ── Approve endpoint ────────────────────────────────────────────────────────

def _w(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    dirs = {k: tmp_path / k for k in ("brands", "topics", "generated")}
    for d in dirs.values():
        d.mkdir()
    monkeypatch.setattr(onboarding_app, "BRANDS_DIR", dirs["brands"])
    monkeypatch.setattr(onboarding_app, "TOPICS_DIR", dirs["topics"])
    monkeypatch.setattr(onboarding_app, "GENERATED_DIR", dirs["generated"])
    monkeypatch.setattr(onboarding_app, "_sync", lambda *a, **k: None)
    onboarding_app.app.dependency_overrides[onboarding_app.api_auth] = lambda: None
    monkeypatch.setattr(emailer, "send_delivery_email", lambda **kw: "email-1")
    monkeypatch.setenv("WP_TEST_PASSWORD", "x")
    _w(dirs["brands"] / "ada.yaml", {"brand_id": "ada", "client_name": "Ada", "client_email": "a@example.com",
                                     "package_size": 8, "publishing": [WP]})
    _w(dirs["generated"] / "ada" / "r1.yaml", _article(status="pending_review"))
    yield TestClient(onboarding_app.app), dirs
    onboarding_app.app.dependency_overrides.clear()


def test_approve_emails_then_publishes_and_retry_fixes_failure(app_env, monkeypatch):
    client, dirs = app_env
    responses = [httpx.Response(500, text="boom"), httpx.Response(201, json={"id": 7, "link": "https://b/7"})]
    real_client = httpx.Client
    monkeypatch.setattr(publishing.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(lambda r: responses.pop(0))))

    r = client.post("/api/brands/ada/generated/r1/approve")
    assert r.status_code == 200
    assert r.json()["email_id"] == "email-1"
    assert r.json()["publish"] == {"published": [], "failed": ["blog"]}
    saved = yaml.safe_load((dirs["generated"] / "ada" / "r1.yaml").read_text())
    assert saved["status"] == "approved" and saved["publications"]["blog"]["status"] == "failed"
    assert client.get("/api/brands/ada/generated").json()[0]["publish_failed"] is True

    r = client.post("/api/brands/ada/generated/r1/publish")
    assert r.status_code == 200 and r.json()["published"] == ["blog"]
    saved = yaml.safe_load((dirs["generated"] / "ada" / "r1.yaml").read_text())
    assert saved["publications"]["blog"]["url"] == "https://b/7"
    assert saved["publications"]["blog"]["attempts"] == 2


def test_publish_endpoint_refuses_unapproved(app_env):
    client, _ = app_env
    assert client.post("/api/brands/ada/generated/r1/publish").status_code == 400


# ── GitHub repo ─────────────────────────────────────────────────────────────

GH = {"id": "site", "type": "github", "repo": "acme/acme-site", "token_env": "GH_TEST_TOKEN",
      "path": "src/content/blog/{date}-{slug}.md", "post_url": "https://acme.com/blog/{slug}/"}


def test_github_commits_markdown_post_with_front_matter(monkeypatch):
    monkeypatch.setenv("GH_TEST_TOKEN", "ghp_x")
    calls = []

    def handler(r):
        if r.method == "GET":
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(201, json={"commit": {"sha": "abc123"}, "content": {"html_url": "https://gh/x"}})

    f = _factory(handler, calls)
    pubs = publishing.publish_article(brand={"client_name": "Ada Lovelace", "publishing": [GH]},
                                      article=_article(), run_id="r", client_factory=f)
    assert pubs["site"]["status"] == "draft"
    assert pubs["site"]["remote_id"] == "abc123"
    assert pubs["site"]["path"] == "src/content/blog/2026-11-23-my-title.md"
    assert pubs["site"]["url"] == "https://acme.com/blog/my-title/"

    put = calls[1]
    assert put.method == "PUT"
    assert str(put.url) == "https://api.github.com/repos/acme/acme-site/contents/src/content/blog/2026-11-23-my-title.md"
    assert put.headers["authorization"] == "Bearer ghp_x"
    body = json.loads(put.content)
    assert body["branch"] == "main"
    text = base64.b64decode(body["content"]).decode()
    front, md = text.split("---\n", 2)[1:]
    meta = yaml.safe_load(front)
    assert meta["title"] == "My Title" and meta["draft"] is True and meta["author"] == "Ada Lovelace"
    assert "# My Title" not in md and "## Section" in md


def test_github_never_overwrites_existing_file(monkeypatch):
    monkeypatch.setenv("GH_TEST_TOKEN", "ghp_x")
    calls = []
    f = _factory(lambda r: httpx.Response(200, json={"sha": "old"}), calls)
    pubs = publishing.publish_article(brand={"publishing": [GH]}, article=_article(), run_id="r", client_factory=f)
    assert pubs["site"]["status"] == "failed" and "already exists" in pubs["site"]["error"]
    assert [c.method for c in calls] == ["GET"]


def test_github_rejects_path_traversal(monkeypatch):
    monkeypatch.setenv("GH_TEST_TOKEN", "ghp_x")
    calls = []
    f = _factory(lambda r: httpx.Response(404), calls)
    bad = {**GH, "path": "../{slug}.md"}
    pubs = publishing.publish_article(brand={"publishing": [bad]}, article=_article(), run_id="r", client_factory=f)
    assert pubs["site"]["status"] == "failed" and calls == []
