# Content Factory ("Said By") — Project Plan

## What it is
An AI-powered ghostwriting service (brand: **Said By**, live at **saidby.co**) that onboards clients, generates recurring content (blog posts + short snippets) in each client's voice, emails the operator for review, and delivers approved content to clients. Fully automated via a daily GitHub Actions scheduler.

---

## Architecture

```
Public homepage (saidby.co) → /onboard intake form (public)
  → submission saved + operator emailed
  → operator reviews & ACTIVATES in /admin (protected)
      → auto-generates topics (Claude) + sends welcome email with topic list
  → operator marks "plan confirmed" once client replies
      → client added to scheduler (plan_confirmed gate)
  → GitHub Actions scheduler (daily, 7am UTC)
      → for each confirmed client due today: picks next approved topic
      → generates article via Claude (voice-matched, optionally book-grounded)
      → commits to repo + emails operator for review
  → Operator reviews in /admin
      → Approve → personalized delivery email to client (Resend)
      → Reject → topic returns to queue for regeneration
```

All runtime file writes (brands, topics, generated, submissions, references) are
**synced to GitHub** via the Contents API (`content_factory/github_sync.py`) so they
survive Railway's ephemeral filesystem and the scheduler can read them.

### Key files
| File | Purpose |
|---|---|
| `onboarding_app.py` | FastAPI backend — auth, all API endpoints, serves pages |
| `index.html` / `login.html` / `onboard.html` | Public homepage / admin login / client intake form |
| `onboarding.html` | Admin SPA — dashboard, Progress/Profile/Topics/Content tabs, submissions |
| `scheduler.py` | Daily scheduler — loops confirmed clients, fires generation |
| `integrations/claude_adapters.py` | **Claude** LLM wrapper (Sonnet 4.6, structured JSON, cached book grounding) |
| `integrations/openai_adapters.py` | `make_llm()` dispatch (defaults Claude); OpenAI kept for **images only** |
| `content_factory/article_writer.py` | Article writer (long blog + short snippet) |
| `content_factory/topic_generator.py` | Topic generation from brand profile |
| `content_factory/content_runner.py` | End-to-end: topic → article → save → review email |
| `content_factory/references.py` | PDF book → text extraction + per-brand storage (grounding) |
| `content_factory/emailer.py` | Resend emails (new-submission, welcome, review, delivery) |
| `content_factory/github_sync.py` | Syncs runtime file writes back to GitHub |
| `content_factory/models.py` | Pydantic schemas for brand profiles |
| `.github/workflows/scheduler.yml` | GitHub Actions daily cron |

### Data directories (all git-synced)
| Path | Contents |
|---|---|
| `content_factory/brands/` | One YAML per client (brand profile) |
| `content_factory/submissions/` | Public intake submissions (pending → activated) |
| `content_factory/topics/` | Topic lists per client (pending_approval → approved) |
| `content_factory/generated/` | Generated articles (pending_review/approved/rejected) |
| `content_factory/references/` | Extracted book/manuscript text per client (`<brand_id>.txt`) |
| `content_factory/requests/` | Auto-generated content request YAMLs |

---

## Content packages & cadence
- Packages: **8** (Starter) / **16** (Standard) / **24** (Premium)
- Cadence: **1× or 2× per week**
- Slot types: `long_blog` (~900–1,200 words) · `short_snippet` (~200–280 words)

## Content styles (brand_archetype)
`mentor_coach`, `author`, `industry_consultant`, `corporate_firm`, `thought_leader`, `reviewer`, `travel_lifestyle`. Tone examples in the intake form change per style.

## Client milestone tracker (Progress tab)
Onboarded → Topics generated → Topics approved → Welcome email → **Plan confirmed** (manual gate) → Articles X/N → Renewal email (when 2 remain).

---

## Infrastructure
| Component | Where |
|---|---|
| Web app / admin UI | Railway → custom domain **saidby.co** (Cloudflare DNS) |
| Scheduler | GitHub Actions (daily cron, 7am UTC) |
| LLM (text) | **Claude Sonnet 4.6** (Anthropic); OpenAI retained for images only |
| Email | Resend, verified domain → sends from **hello@saidby.co** |
| Repo | GitHub (`jiraindira/content_factory`) |

### Environment variables (Railway + GitHub Secrets + local .env)
| Key | Notes |
|---|---|
| `ANTHROPIC_API_KEY` | Required — all text generation |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` (set `claude-opus-4-8` for premium tier) |
| `OPENAI_API_KEY` / `OPENAI_IMAGE_MODEL` | Images only |
| `RESEND_API_KEY` / `FROM_EMAIL` | `Said By <hello@saidby.co>` |
| `OPERATOR_EMAIL` | `jiraindira@gmail.com` |
| `REVIEW_UI_URL` | `https://saidby.co` |
| `GITHUB_TOKEN` / `GITHUB_REPO` | Runtime file sync to repo |
| `SECRET_KEY` / `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Admin session auth |

---

## Completed
- [x] Public homepage, admin login + session auth, public intake form
- [x] Onboarding intake → activate flow (auto topic gen + welcome email on activation)
- [x] Brand profile schema; 7 content styles; 7 audience options
- [x] AI topic generator + review/approval UI
- [x] Voice-matched article writer (long blog + short snippet)
- [x] Review UI (approve/reject) + on-demand "Generate" button
- [x] Personalized emails (welcome with topics, review, delivery with progress)
- [x] Client milestone tracker (Progress tab) + dashboard + tabbed admin
- [x] GitHub Actions daily scheduler with plan_confirmed gate
- [x] Railway deployment + custom domain saidby.co + Resend domain
- [x] GitHub sync layer (survives Railway redeploys)
- [x] Mobile-responsive admin
- [x] **Migrated all text generation to Claude (Sonnet 4.6)**
- [x] **PDF book upload + full-context grounding for author clients**

## To-do

### Business priorities (do before more building)
- [ ] Set pricing on saidby.co homepage
- [ ] Onboard first paying clients (Alisa, Jit) — upload Jit's book, confirm plans
- [ ] Pitch 2–3 people in network who fit the profile
- [ ] Define renewal flow — what happens after a package ends? (revenue)

### Marketing — Said By produces content for Said By
- [ ] Create `saidby` brand profile in admin (eat own dog food)
- [ ] Automate LinkedIn + Instagram posts via scheduler
- [ ] LinkedIn publishing integration (post directly, not just email)

### Product (after first paying clients)
- [ ] Cross-client "All content" overview (chip queued)
- [ ] Client portal — read-only view of plan + delivered articles
- [ ] Regenerate single topic button
- [ ] OCR fallback for scanned-PDF books (currently text-PDF only)

---

## Known limitations
- Book upload requires **text-based PDFs** (scanned-image PDFs extract almost nothing — guarded with an error)
- LinkedIn blocked by robots.txt — brand context uses homepage only
- Delivery emails: now send to real client addresses (Resend domain verified)
