# Content Factory — Project Plan

## What it is
An AI-powered content factory that onboards clients, generates recurring social media content (blog posts and short snippets), emails the operator for review, and delivers approved content to clients. Fully automated via a daily GitHub Actions scheduler.

---

## Architecture

```
Client onboarding (Railway UI)
  → Brand profile YAML saved to repo
  → Topics generated via OpenAI + approved in UI
  → GitHub Actions scheduler (daily, 7am UTC)
      → picks next approved topic per client
      → generates article via OpenAI (voice-matched)
      → commits to repo + emails operator for review
  → Operator reviews in hosted UI (Railway)
      → Approve → sends to client via Resend
      → Reject → topic returns to queue
```

### Key files
| File | Purpose |
|---|---|
| `onboarding_app.py` | FastAPI backend — all API endpoints + serves UI |
| `onboarding.html` | Admin onboarding + review UI |
| `scheduler.py` | Daily scheduler — loops all clients, fires generation |
| `content_factory/article_writer.py` | LLM article writer (long blog + short snippet) |
| `content_factory/content_runner.py` | End-to-end runner: topic → article → email |
| `content_factory/topic_generator.py` | AI topic generation from brand profile |
| `content_factory/emailer.py` | Resend email integration (review + delivery) |
| `content_factory/models.py` | Pydantic schemas for brand profiles |
| `.github/workflows/scheduler.yml` | GitHub Actions cron workflow |

### Data directories
| Path | Contents |
|---|---|
| `content_factory/brands/` | One YAML per client (brand profile) |
| `content_factory/topics/` | Approved topic lists per client |
| `content_factory/generated/` | Generated articles (pending/approved/rejected) |
| `content_factory/requests/` | Auto-generated content request YAMLs |
| `content_factory/artifacts/` | Cached brand context (from web scraping) |

---

## Content packages
- **8 articles** — Starter
- **16 articles** — Standard
- **24 articles** — Premium

## Cadence options
- 1× per week
- 2× per week

## Content types per slot
- `long_blog` — 900–1,200 words, prose, 3–4 sections
- `short_snippet` — 200–280 words, punchy, conversational

---

## Creator roles
| Value | Description |
|---|---|
| `mentor_coach` | Frameworks, lessons, personal growth |
| `product_ranker` | Best-of lists, top 10s, comparisons |
| `product_guide` | Deep expert on one product/niche |
| `reviewer` | Opinionated evaluations |
| `travel_guide` | Destination and experience storytelling |

---

## Infrastructure
| Component | Where |
|---|---|
| Web app / admin UI | Railway (`web-production-319f9.up.railway.app`) |
| Scheduler | GitHub Actions (daily cron, 7am UTC) |
| Email | Resend (sandbox → own domain later) |
| LLM | OpenAI (`gpt-4.1-mini`) |
| Repo | GitHub (`jiraindira/content_factory`) |

### Environment variables required
| Key | Where set |
|---|---|
| `OPENAI_API_KEY` | Railway + GitHub Secrets |
| `OPENAI_MODEL` | Railway + GitHub Secrets (`gpt-4.1-mini`) |
| `RESEND_API_KEY` | Railway + GitHub Secrets |
| `OPERATOR_EMAIL` | Railway + GitHub Secrets (`jiraindira@gmail.com`) |
| `REVIEW_UI_URL` | Railway + GitHub Secrets (Railway URL) |

---

## Completed
- [x] Client onboarding UI (9-section interview form)
- [x] Brand profile schema (creator role, audience, tone, persona, cadence, package)
- [x] AI topic generator (OpenAI, N topics based on package size)
- [x] Topic review + approval UI
- [x] LLM article writer (voice-matched from brand profile)
- [x] Content runner (topic → article → save → email)
- [x] Resend email integration (review email to operator, delivery to client)
- [x] Review UI (approve/reject with article reader)
- [x] GitHub Actions daily scheduler
- [x] Railway deployment
- [x] Public homepage + admin auth (session login, protected /admin)
- [x] Public client intake form (/onboard) with submission → operator email → activate flow

## To-do
- [ ] Cross-client "All content" overview (see all articles across clients in one view)
- [ ] Add custom domain to Resend (remove sandbox restriction)
- [ ] Content delivery to client website / LinkedIn (not just email)
- [ ] Regenerate single topic button in UI (without running full scheduler)

---

## Known limitations
- Resend sandbox: delivery emails go to operator until custom domain is added
- LinkedIn blocked by robots.txt — brand context uses homepage only
