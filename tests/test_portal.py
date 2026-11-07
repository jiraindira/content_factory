"""Client portal: email sign-in links, access control, and the overview."""
from __future__ import annotations

import yaml
import pytest
from fastapi.testclient import TestClient

import onboarding_app
from content_factory import emailer, portal


def _w(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    dirs = {k: tmp_path / k for k in ("brands", "submissions", "topics", "generated")}
    for d in dirs.values():
        d.mkdir()
    monkeypatch.setattr(onboarding_app, "BRANDS_DIR", dirs["brands"])
    monkeypatch.setattr(onboarding_app, "SUBMISSIONS_DIR", dirs["submissions"])
    monkeypatch.setattr(onboarding_app, "TOPICS_DIR", dirs["topics"])
    monkeypatch.setattr(onboarding_app, "GENERATED_DIR", dirs["generated"])
    monkeypatch.setattr(onboarding_app, "_portal_login_sent", {})
    sent = []
    monkeypatch.setattr(emailer, "send_portal_login_email", lambda client_email, link: sent.append((client_email, link)))

    _w(dirs["brands"] / "ada.yaml", {
        "brand_id": "ada", "client_name": "Ada Test", "client_email": "Ada@Example.com",
        "plan": "free_preview", "package_size": 2, "plan_confirmed": True,
        "cadence": {"publication_cadence": "weekly"}, "content_slots": [{"day": "mon", "type": "long_blog"}],
    })
    _w(dirs["brands"] / "other.yaml", {"brand_id": "other", "client_email": "other@example.com", "package_size": 8})
    _w(dirs["topics"] / "ada.yaml", {"status": "approved", "topics": [
        {"title": "First", "status": "sent"}, {"title": "Second", "status": "approved"}]})
    _w(dirs["generated"] / "ada" / "2026-11-02_first.yaml",
       {"topic": "First", "status": "approved", "slot_type": "long_blog", "generated_at": "2026-11-02", "content": "# First\n\nHello"})
    _w(dirs["generated"] / "ada" / "2026-11-03_draft.yaml",
       {"topic": "Draft", "status": "pending_review", "content": "secret draft"})
    _w(dirs["generated"] / "other" / "2026-11-02_x.yaml", {"topic": "X", "status": "approved", "content": "not yours"})
    return TestClient(onboarding_app.app), sent


def _sign_in(client, email="ada@example.com"):
    token = portal.make_login_token(email, onboarding_app.SECRET_KEY)
    r = client.get(f"/portal/auth?token={token}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/portal"


def test_login_link_only_sent_to_known_emails_and_throttled(env):
    client, sent = env
    assert client.post("/api/portal/login", json={"email": "stranger@example.com"}).json() == {"sent": True}
    assert sent == []  # same response, but no email
    client.post("/api/portal/login", json={"email": " ADA@example.com "})
    client.post("/api/portal/login", json={"email": "ada@example.com"})  # within cooldown
    assert len(sent) == 1 and sent[0][0] == "ada@example.com"
    assert "/portal/auth?token=" in sent[0][1]
    assert client.post("/api/portal/login", json={"email": "nope"}).status_code == 400


def test_token_roundtrip_and_tamper():
    tok = portal.make_login_token("A@b.co", "s3cret")
    assert portal.read_login_token(tok, "s3cret") == "a@b.co"
    assert portal.read_login_token(tok, "other-secret") is None
    assert portal.read_login_token(tok + "x", "s3cret") is None
    assert portal.read_login_token(tok, "s3cret", max_age=-1) is None


def test_bad_token_redirects_to_expired(env):
    client, _ = env
    r = client.get("/portal/auth?token=garbage", follow_redirects=False)
    assert r.headers["location"] == "/portal?error=expired"
    assert client.get("/api/portal/me").status_code == 401


def test_overview_shows_only_own_delivered_articles(env):
    client, _ = env
    _sign_in(client)
    me = client.get("/api/portal/me").json()
    assert [b["brand_id"] for b in me["brands"]] == ["ada"]
    b = me["brands"][0]
    assert b["delivered"] == 1 and b["package_size"] == 2 and b["stage"] == "in_progress"
    assert [a["title"] for a in b["articles"]] == ["First"]  # pending draft hidden
    assert [t["status"] for t in b["topics"]] == ["Delivered", "Upcoming"]
    assert {o["id"] for o in b["upgrade_options"]} == {"starter", "standard", "premium"}


def test_article_access_control(env):
    client, _ = env
    _sign_in(client)
    assert client.get("/api/portal/articles/ada/2026-11-02_first").json()["content"].startswith("# First")
    assert client.get("/api/portal/articles/ada/2026-11-03_draft").status_code == 404  # not approved
    assert client.get("/api/portal/articles/other/2026-11-02_x").status_code == 404   # someone else's
    client.get("/portal/logout", follow_redirects=False)
    assert client.get("/api/portal/articles/ada/2026-11-02_first").status_code == 401
