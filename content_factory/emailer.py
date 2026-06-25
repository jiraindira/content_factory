"""
Email delivery via Resend.

Two send functions:
  send_review_email  — content generated, sent to operator for review
  send_delivery_email — content approved, sent to client
"""
from __future__ import annotations

import os
import re
from dotenv import load_dotenv

load_dotenv()

import resend

resend.api_key = os.environ.get("RESEND_API_KEY", "").strip()

FROM_ADDRESS = os.environ.get("FROM_EMAIL", "Said By <onboarding@resend.dev>")
OPERATOR_EMAIL = os.environ.get("OPERATOR_EMAIL", "").strip()
REVIEW_UI_URL = os.environ.get("REVIEW_UI_URL", "http://localhost:8502").strip()


def _clean(text: str) -> str:
    """Normalise curly quotes and dashes to safe HTML equivalents."""
    return (text
        .replace('‘', '&#8216;').replace('’', '&#8217;')
        .replace('“', '&#8220;').replace('”', '&#8221;')
        .replace('–', '&ndash;').replace('—', '&mdash;')
    )


def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML for email bodies (headings, bold, paragraphs)."""
    lines, html = text.splitlines(), []
    for line in lines:
        line = _clean(line.rstrip())
        if line.startswith("### "):
            html.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            html.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html.append(f"<h1>{line[2:]}</h1>")
        elif line == "":
            html.append("<br/>")
        else:
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"\*(.+?)\*", r"<em>\1</em>", line)
            html.append(f"<p>{line}</p>")
    return "\n".join(html)


def _base_style() -> str:
    return """
    <style>
      body { font-family: Georgia, serif; max-width: 680px; margin: 0 auto; padding: 32px 24px; color: #1f2937; }
      h1 { font-size: 1.6rem; margin-bottom: 0.5rem; }
      h2 { font-size: 1.3rem; margin-top: 1.5rem; }
      h3 { font-size: 1.1rem; margin-top: 1.2rem; }
      p  { line-height: 1.7; margin: 0.6rem 0; }
      .meta { font-size: 0.8rem; color: #6b7280; margin-bottom: 2rem; border-bottom: 1px solid #e5e7eb; padding-bottom: 1rem; }
      .banner { background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 6px; padding: 16px 20px; margin-bottom: 2rem; }
      .banner a { color: #4f46e5; font-weight: 600; }
      .content { border-top: 2px solid #e5e7eb; padding-top: 1.5rem; margin-top: 1.5rem; }
      .footer { font-size: 0.75rem; color: #9ca3af; margin-top: 3rem; border-top: 1px solid #f3f4f6; padding-top: 1rem; }
    </style>
    """


def send_review_email(
    *,
    client_name: str,
    client_brand_id: str,
    topic_title: str,
    content_markdown: str,
    slot_type: str = "long_blog",
    brand: dict | None = None,
    article_number: int | None = None,
    package_size: int | None = None,
) -> str:
    """Send generated content to the operator for review. Returns Resend message ID."""
    if not OPERATOR_EMAIL:
        raise ValueError("OPERATOR_EMAIL is not set in .env")

    topic_title = " ".join(topic_title.split())
    content_type = "Long blog" if slot_type == "long_blog" else "Short snippet"
    html_content = _md_to_html(content_markdown)

    # Build reviewer context block from brand profile
    brand = brand or {}
    about = ((brand.get("topic_policy") or {}).get("allowlist") or [""])[0]
    audience_ctx = (brand.get("audience") or {}).get("audience_context", "")
    domains = brand.get("domains_supported") or []
    persona_cfg = (brand.get("persona_by_domain") or {}).get(domains[0] if domains else "", {})
    persona = (persona_cfg.get("primary_persona") or "").replace("_", " ")

    article_label = ""
    if article_number and package_size:
        article_label = f" &nbsp;·&nbsp; <strong>Article {article_number} of {package_size}</strong>"

    context_rows = []
    if about:
        context_rows.append(f"<tr><td style='color:#6b7280;padding:3px 12px 3px 0;font-size:0.8rem;white-space:nowrap'>Niche</td><td style='font-size:0.8rem;color:#111827'>{_clean(about[:120])}</td></tr>")
    if audience_ctx:
        context_rows.append(f"<tr><td style='color:#6b7280;padding:3px 12px 3px 0;font-size:0.8rem;white-space:nowrap'>Audience</td><td style='font-size:0.8rem;color:#111827'>{_clean(audience_ctx)}</td></tr>")
    if persona:
        context_rows.append(f"<tr><td style='color:#6b7280;padding:3px 12px 3px 0;font-size:0.8rem;white-space:nowrap'>Voice</td><td style='font-size:0.8rem;color:#111827'>{persona.title()}</td></tr>")

    context_block = ""
    if context_rows:
        context_block = f"""
        <table style="border-collapse:collapse;margin:0.75rem 0 0">
          {''.join(context_rows)}
        </table>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <style>
    body {{ font-family: Georgia, serif; max-width: 680px; margin: 0 auto; padding: 32px 24px; color: #1f2937; background:#fff; }}
    h1 {{ font-size: 1.5rem; font-weight: 700; margin: 1.5rem 0 0.5rem; line-height: 1.3; }}
    h2 {{ font-size: 1.2rem; font-weight: 700; margin: 1.8rem 0 0.4rem; color: #111827; }}
    h3 {{ font-size: 1rem; font-weight: 600; margin: 1.4rem 0 0.3rem; }}
    p  {{ line-height: 1.8; margin: 0.8rem 0; }}
    .banner {{ background:#eef2ff; border:1px solid #c7d2fe; border-radius:8px; padding:16px 20px; margin-bottom:1.5rem; font-family:sans-serif; }}
    .banner strong {{ color:#1e1b4b; }}
    .banner a {{ color:#4f46e5; font-weight:600; text-decoration:none; }}
    .banner small {{ color:#6b7280; font-size:0.78rem; }}
    .meta {{ font-family:sans-serif; font-size:0.78rem; color:#6b7280; padding:0.75rem 0; border-bottom:1px solid #f3f4f6; margin-bottom:1.5rem; }}
    .content {{ border-top:2px solid #e5e7eb; padding-top:1.5rem; margin-top:1.5rem; }}
    .footer {{ font-size:0.72rem; color:#9ca3af; margin-top:3rem; border-top:1px solid #f3f4f6; padding-top:1rem; font-family:sans-serif; }}
  </style>
</head>
<body>
  <div class="banner">
    <strong>✦ Ready for review</strong> &nbsp;·&nbsp; {client_name}{article_label}<br/>
    <small>Approve or reject at <a href="{REVIEW_UI_URL}/admin">{REVIEW_UI_URL}/admin</a></small>
    {context_block}
  </div>

  <div class="meta">
    <strong style="color:#374151">{content_type}</strong> &nbsp;·&nbsp; Written for: {client_name}
  </div>

  <div class="content">
    {html_content}
  </div>

  <div class="footer">
    Said By · Generated for {client_name} · <a href="{REVIEW_UI_URL}/admin" style="color:#6366f1">Review in admin</a>
  </div>
</body>
</html>"""

    params: resend.Emails.SendParams = {
        "from": FROM_ADDRESS,
        "to": [OPERATOR_EMAIL],
        "subject": f"[Review] {topic_title} — {client_name}",
        "html": html,
    }
    response = resend.Emails.send(params)
    return response["id"]


def send_welcome_email(*, brand: dict, topics: list[str]) -> str:
    """Send welcome email to client with their approved topic list."""
    if not OPERATOR_EMAIL:
        raise ValueError("OPERATOR_EMAIL is not set in .env")

    client_name = brand.get("client_name") or brand.get("brand_id", "")
    first_name = client_name.split()[0] if client_name else "there"
    client_email = brand.get("client_email", "")
    if not client_email:
        raise ValueError("client_email not set on brand profile")

    sandbox = "resend.dev" in FROM_ADDRESS
    to_address = OPERATOR_EMAIL if sandbox else client_email

    slots = brand.get("content_slots", [])
    cadence = brand.get("cadence", {})
    freq = cadence.get("publication_cadence", "weekly")
    freq_label = "twice a week" if freq == "twice_weekly" else "once a week"
    days = [s.get("day", "").capitalize() for s in slots]
    days_label = " and ".join(days) if days else "your scheduled days"
    package_size = brand.get("package_size", 8)

    # Pull niche + audience for personalisation
    about = ((brand.get("topic_policy") or {}).get("allowlist") or [""])[0]
    audience_ctx = (brand.get("audience") or {}).get("audience_context", "")

    # Build topics list — clean quotes before rendering
    def clean(t: str) -> str:
        return t.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')

    topics_html = "".join(
        f'<li style="margin:0.6rem 0;color:#374151;line-height:1.5">{clean(t)}</li>'
        for t in topics
    )

    # Personalised intro line based on what they write about
    niche_line = ""
    if about:
        niche_line = f'<p style="color:#4b5563;font-style:italic;border-left:3px solid #6366f1;padding-left:1rem;margin:1.5rem 0">{clean(about)}</p>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width"/>
  <style>
    body {{ font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 40px 24px; color: #1f2937; line-height: 1.8; background: #fff; }}
    h1 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 0.25rem; color: #111827; }}
    p {{ margin: 1rem 0; font-size: 1rem; }}
    ol {{ padding-left: 1.25rem; margin: 1.5rem 0; }}
    strong {{ color: #111827; }}
    .divider {{ border: none; border-top: 1px solid #e5e7eb; margin: 2rem 0; }}
    .footer {{ font-size: 0.75rem; color: #9ca3af; margin-top: 3rem; }}
    .badge {{ display: inline-block; background: #eef2ff; color: #4338ca; font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 999px; font-family: sans-serif; letter-spacing: 0.05em; text-transform: uppercase; }}
  </style>
</head>
<body>
  <p><span class="badge">Said By</span></p>

  <h1>{first_name} — you're in.</h1>

  <p>We've reviewed your submission and we want to be direct: <strong>this is exactly the kind of work we love doing.</strong></p>

  {niche_line}

  <p>Your voice, your audience{f', your focus on {audience_ctx}' if audience_ctx else ''} — it's a compelling brief. And we're ready to run with it.</p>

  <hr class="divider"/>

  <p><strong>Here's your content plan — {package_size} articles:</strong></p>

  <ol>{topics_html}</ol>

  <p>These will go out <strong>{freq_label}</strong>, every <strong>{days_label}</strong>. Each piece written in your voice, sent to you for approval before it goes anywhere.</p>

  <hr class="divider"/>

  <p><strong>Ready to get started?</strong></p>
  <p>Simply reply to this email to confirm and we'll kick things off. The first article will be in your inbox before you know it.</p>

  <p style="margin-top:2.5rem">We're genuinely excited about this one.</p>

  <p>— Jiraindira<br/><span style="color:#9ca3af;font-size:0.9rem">Said By</span></p>

  <div class="footer">Said By · <a href="{REVIEW_UI_URL}" style="color:#6366f1">{REVIEW_UI_URL}</a></div>
</body>
</html>"""

    subject = f"{first_name} — your content plan is confirmed"
    if sandbox:
        subject = f"[SANDBOX → {client_email}] {subject}"

    params: resend.Emails.SendParams = {
        "from": FROM_ADDRESS,
        "to": [to_address],
        "subject": subject,
        "html": html,
    }
    response = resend.Emails.send(params)
    return response["id"]


def send_new_submission_email(*, submission: dict) -> str:
    """Notify operator that a new client intake was submitted."""
    if not OPERATOR_EMAIL:
        raise ValueError("OPERATOR_EMAIL is not set in .env")

    name = submission.get("client_name", "Unknown")
    email = submission.get("client_email", "")
    role = submission.get("brand_archetype", "").replace("_", " ").title()
    about = submission.get("about", "")
    review_url = f"{REVIEW_UI_URL}/admin"

    html = f"""
    <!DOCTYPE html><html><head>{_base_style()}</head><body>
    <div class="banner">
      ✦ New client intake submitted<br/>
      <small>Review and activate at: <a href="{review_url}">{review_url}</a></small>
    </div>
    <h2 style="margin-top:0">{name}</h2>
    <div class="meta">
      <strong>Email:</strong> {email} &nbsp;·&nbsp;
      <strong>Role:</strong> {role}
    </div>
    <p><strong>What they write about:</strong><br/>{about}</p>
    <div class="footer">Content Factory · New submission notification</div>
    </body></html>
    """

    params: resend.Emails.SendParams = {
        "from": FROM_ADDRESS,
        "to": [OPERATOR_EMAIL],
        "subject": f"New intake: {name}",
        "html": html,
    }
    response = resend.Emails.send(params)
    return response["id"]


def send_delivery_email(
    *,
    client_name: str,
    client_email: str,
    topic_title: str,
    content_markdown: str,
    slot_type: str = "long_blog",
    article_number: int | None = None,
    package_size: int | None = None,
    next_publish_day: str | None = None,
) -> str:
    """Send approved content to the client. Returns Resend message ID."""
    if not client_email:
        raise ValueError("client_email is empty")

    topic_title = " ".join(topic_title.split())
    first_name = client_name.split()[0] if client_name else client_name
    content_type = "long-form article" if slot_type == "long_blog" else "short post"

    sandbox = "resend.dev" in FROM_ADDRESS
    to_address = OPERATOR_EMAIL if sandbox else client_email
    html_content = _md_to_html(content_markdown)

    sandbox_banner = ""
    if sandbox:
        sandbox_banner = f"""<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:6px;padding:12px 16px;margin-bottom:24px;font-size:0.8rem;color:#92400e;font-family:sans-serif">
          <strong>Sandbox</strong> — would go to <strong>{_clean(client_email)}</strong>
        </div>"""

    # Progress note
    progress_note = ""
    if article_number and package_size:
        next_line = f" Your next piece is coming on <strong>{next_publish_day}</strong>." if next_publish_day else ""
        progress_note = f"""
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px 20px;margin:2rem 0;font-family:sans-serif;font-size:0.85rem;color:#374151;line-height:1.6">
          📬 &nbsp;This is your <strong>article {article_number} of {package_size}</strong> — you're {round(article_number/package_size*100)}% through your content plan.{next_line}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width"/>
  <style>
    body {{ font-family: Georgia, serif; max-width: 680px; margin: 0 auto; padding: 32px 24px; color: #1f2937; background:#fff; line-height:1.8; }}
    h1 {{ font-size: 1.5rem; font-weight: 700; margin: 1.5rem 0 0.5rem; line-height: 1.3; }}
    h2 {{ font-size: 1.2rem; font-weight: 700; margin: 1.8rem 0 0.4rem; }}
    h3 {{ font-size: 1rem; font-weight: 600; margin: 1.4rem 0 0.3rem; }}
    p  {{ margin: 0.9rem 0; }}
    .divider {{ border:none; border-top:1px solid #e5e7eb; margin:2rem 0; }}
    .footer {{ font-size:0.72rem; color:#9ca3af; margin-top:3rem; border-top:1px solid #f3f4f6; padding-top:1rem; font-family:sans-serif; }}
  </style>
</head>
<body>
  {sandbox_banner}

  <p style="font-family:sans-serif;font-size:0.8rem;color:#6b7280;margin-bottom:0.25rem">
    <strong style="color:#4f46e5">✦ Said By</strong>
  </p>

  <p style="font-family:sans-serif;font-size:1.1rem;font-weight:600;color:#111827;margin:0 0 0.25rem">
    Hi {first_name}! 👋
  </p>

  <p style="font-family:sans-serif;color:#374151;margin:0 0 1.5rem">
    Your latest {content_type} is ready — this one is on <strong>{_clean(topic_title)}</strong>. Take a read and let us know what you think.
  </p>

  <hr class="divider"/>

  {html_content}

  <hr class="divider"/>

  {progress_note}

  <p style="font-family:sans-serif;font-size:0.9rem;color:#374151;margin-top:1.5rem">
    As always, feel free to reply with any feedback — we love hearing from you.
  </p>

  <p style="font-family:sans-serif;margin-top:2rem">
    — Jiraindira<br/>
    <span style="color:#9ca3af;font-size:0.85rem">Said By</span>
  </p>

  <div class="footer">Said By · Ghostwriting for {client_name}</div>
</body>
</html>"""

    subject = f"Your latest article is ready, {first_name}!"
    if sandbox:
        subject = f"[SANDBOX → {client_email}] {subject}"

    params: resend.Emails.SendParams = {
        "from": FROM_ADDRESS,
        "to": [to_address],
        "subject": subject,
        "html": html,
    }
    response = resend.Emails.send(params)
    return response["id"]
