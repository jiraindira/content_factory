# TheProductWheel Execution Plan (Factory → Managed Site)

Date: 2026-02-23  
Last updated: 2026-02-23  
Status: Milestones 0–6 complete. Manual import → package → PR delivery is live. Next focus: LLM-required editorial quality parity (intro + pick bodies + formatting).

## Repo Split (Current State)

As of 2026-02-23, this system is split into two GitHub repos:

- **Factory**: https://github.com/jiraindira/content_factory
- **Managed site (Astro)**: https://github.com/jiraindira/theproductwheel

This file lives in the historical monorepo workspace, but the active source of truth is now the two repos above.

Local convention (canonical checkouts going forward):
- Factory: `.../content_factory`
- Managed site: `.../theproductwheel` (use this as the primary working checkout)

## Goal

Split “content generation” from “publishing/display”:

- **Content Factory repo**: LLM-heavy generation, produces reviewable content packages.
- **TheProductWheel Managed Site repo (Astro)**: owns publishing + assets (hero + pick images).
- **Delivery mechanism**: Factory opens Git PRs against the managed-site repo.
- **Rendering contract**: picks come from structured frontmatter `picks[]`.

This plan is milestone-gated. Work only starts on the next milestone after explicit approval.

## Non-Goals (for now)

- No extra destinations beyond blog article (email/linkedin can come later).
- No new UI/UX features in the Astro site.
- No “direct write into site tree” from factory (delivery is PR-based).

## Current Baseline (what exists today)

- Factory scaffolding + validation:
  - Brand/request scaffolding: [content_factory/onboarding.py](content_factory/onboarding.py)
  - Request validation: [content_factory/validation.py](content_factory/validation.py)
  - Factory CLI: [content_factory/cli.py](content_factory/cli.py)
- Factory blog output currently writes markdown into factory outputs (not into the Astro content directory):
  - Blog adapter: [content_factory/adapters/blog_adapter.py](content_factory/adapters/blog_adapter.py)
  - Outputs/dispatch: [content_factory/adapters/dispatch.py](content_factory/adapters/dispatch.py)
- Astro managed site rendering expectations:
  - Content collection schema: [site/src/content.config.ts](site/src/content.config.ts)
  - Post page rendering (picks frontmatter preferred; markdown fallback exists): [site/src/pages/posts/[...slug].astro](site/src/pages/posts/[...slug].astro)
  - Taxonomy model: [site/src/lib/taxonomy.ts](site/src/lib/taxonomy.ts)
  - Taxonomy data: [site/src/content/site/taxonomy.json](site/src/content/site/taxonomy.json)
- Manual pipeline currently writes directly into the Astro site tree (legacy for future architecture):
  - Entrypoint: [scripts/write_manual_post.py](scripts/write_manual_post.py)
  - Writer: [pipeline/manual_post_writer.py](pipeline/manual_post_writer.py)

## Key Decisions (locked)

- Repo split: now (separate factory vs managed site).
- Delivery: Git PR flow from factory → managed site.
- Picks format: frontmatter `picks[]` is the source of truth.
- Images: managed site generates/enriches hero + pick images.

## Milestones

### Milestone 0 — Contracts + Repo Boundaries (Approval Required)

Objective: Define a stable handoff contract so both repos can evolve independently.

Deliverables:
- “Content Package v1” contract document:
  - Required fields for managed-site rendering (title/description/publishedAt/categories/products/picks).
  - File layout (manifest + content files).
  - Slug rules and publish-date rules.
  - What is content-only vs publish-ready.
- Repo boundary definition:
  - Which modules belong to factory vs managed site (and why).
  - What shared logic, if any, is allowed (default: none; copy as needed).

Acceptance criteria:
- Contract explicitly maps to the Astro schema in [site/src/content.config.ts](site/src/content.config.ts).
- Contract explicitly supports structured `picks[]` that the managed site can render without parsing markdown sections.
- Contract states that images are managed-site-owned, and defines placeholders/fields (if needed) without requiring factory downloads.

Definition of Done:
- Contract is written, reviewed, and considered “v1 locked”.
- Repos exist with empty/stub structure ready for Milestone 1.

Status: Done (implemented in this repo as a stepping stone).

---

### Milestone 1 — TheProductWheel Becomes a Valid Factory Brand (Approval Required)

Objective: Establish `brand_id: the_product_wheel` as a working first-class factory brand.

Deliverables:
- One canonical brand YAML at the factory brand path conventions described by [content_factory/onboarding.py](content_factory/onboarding.py).
- One request YAML that matches the brand_id and passes validation per [content_factory/validation.py](content_factory/validation.py).

Acceptance criteria:
- Factory validation passes for the brand + request via the CLI in [content_factory/cli.py](content_factory/cli.py).
- Naming consistency: brand_id matches across brand file and request file.

Definition of Done:
- A factory run can start from this request without manual edits to configs.

Status: Done.

---

### Milestone 2 — Factory Emits “Content Package v1” (No Site Writes) (Approval Required)

Objective: Factory output becomes a reviewable package, not a loose markdown file.

Deliverables:
- Package generator in the factory that produces:
  - A manifest (brand_id, run_id, publish_date, slug, output list).
  - A blog markdown file intended for the managed site.
- Blog markdown includes:
  - Frontmatter fields required by Astro.
  - `products[]` and `picks[]` structured data sufficient for rendering.
  - Taxonomy-compatible categories.

Acceptance criteria:
- Package is deterministic and reproducible per run_id.
- Managed site can apply the package without guessing missing fields.

Definition of Done:
- Running the factory yields a package directory that can be code-reviewed as a single unit.

Status: Done.

---

### Milestone 3 — Managed-Site Hydration (Assets + Finalization) (Approval Required)

Objective: Managed site transforms “content-only” into “publish-ready” (images and any local conventions).

Deliverables:
- Managed-site command that:
  - Ingests Content Package v1.
  - Writes markdown to the Astro posts collection directory.
  - Generates/enriches hero image and pick images and updates frontmatter accordingly.
- Managed site remains the owner of:
  - Pick image download/optimization.
  - Hero generation/selection.

Acceptance criteria:
- After hydration, the post renders correctly in Astro with hero and pick images present.
- No factory-side downloading of images is required.

Definition of Done:
- One command produces a merge-ready set of changes in the managed-site repo.

Status: Done (implemented in-repo; designed to run against an external managed-site checkout via repo_root).

---

### Milestone 4 — PR Delivery (Factory → Managed Site) (Approval Required)

Objective: Fully automated PR-based publishing workflow.

Deliverables:
- Factory delivery step that:
  - Clones/updates the managed-site repo.
  - Applies the content package.
  - Runs managed-site hydration.
  - Commits to a branch and opens a PR.

Acceptance criteria:
- One factory run produces exactly one PR containing all required changes (markdown + assets).
- PR is reviewable and mergeable without additional manual steps.

Definition of Done:
- Publishing is an “approve + merge PR” workflow.

Status: Next.

Update (2026-02-18): Done.
- PR: https://github.com/jiraindira/theproductwheel/pull/1 (merged)

---

## Next Steps (Practical Workflow)

### 1) Local setup

- Clone both repos:
  - `git clone https://github.com/jiraindira/content_factory`
  - `git clone https://github.com/jiraindira/theproductwheel`

### 2) Run tests

- Factory tests:
  - `cd content_factory`
  - `poetry install`
  - `poetry run pytest`

### 3) Managed-site validation + build

- Managed-site content validation is run automatically as part of `npm run build` via `site/scripts/validate_content.mjs`.
- Vercel expects a repo-root `validate_content.py` entrypoint (because the validation scripts call `python validate_content.py`).
- From the managed-site repo:
  - `cd site`
  - `npm install`
  - `npm run build`

### 4) Hydrate a content package into the managed site

Hydration is owned by the managed-site repo.

- From the managed-site repo root:
  - `poetry run python -m scripts.hydrate_content_package --package-dir <path-to-package> --overwrite`

Notes:
- Hero regeneration is only attempted when `OPENAI_API_KEY` is set; otherwise the placeholder hero is used.
- Pick image enrichment runs during hydration unless `--no-pick-images` is provided.

### 5) PR delivery (factory → managed site)

PR delivery runs from the factory repo and should:
- generate a package
- run managed-site hydration in a managed-site checkout
- commit changes to a branch
- push and open a PR

Exact command shape depends on the current factory CLI wrapper (see `scripts/deliver_package_pr.py` in the factory repo).

## Vercel Build Gotchas (Known)

- Astro content collection schema must match frontmatter types. In particular:
  - `products[].rating` and `products[].reviews_count` may be `null` in generated content, so the schema must allow nullable values.

---

### Milestone 5 — Manual Workflow Migrated Behind Factory Requests (Approval Required)

Objective: “Manual post” becomes a request type under the factory umbrella, delivered via PR like everything else.

Deliverables:
- A request type or importer that converts legacy manual inputs into a factory request.
- A run path that produces the same managed-site result quality as the legacy manual writer, but through the package + PR pipeline.

Acceptance criteria:
- Equivalent post output (structure + rendering) compared to manual pipeline behavior, but delivered via PR.
- Legacy “direct write into site tree” path is deprecated or kept only as managed-site tooling.

Definition of Done:
- TheProductWheel publishing uses factory requests end-to-end.

Status: Done.

Update (2026-02-23): Done.
- PR: https://github.com/jiraindira/theproductwheel/pull/2

---

### Milestone 6 — Local Workspace Alignment (Canonical Managed-Site Checkout) (Approval Required)

Objective: Standardize local development so there is one clear managed-site checkout (`theproductwheel`) and the historical monorepo is treated as docs/archive only.

Deliverables:
- Use `C:\Users\jirai\Documents\Projects\theproductwheel` as the canonical managed-site repo folder.
- Optional cleanup: remove/ignore any temporary checkouts (e.g. `theproductwheel_check`) once no longer needed.
- Update runbooks/commands to reference the canonical path (hydration + PR delivery).
- Optional: create a VS Code multi-root workspace that opens `content_factory` + `theproductwheel` together.

Acceptance criteria:
- `git status` is clean in both repos.
- Factory PR delivery targets the canonical `theproductwheel` path.
- Managed-site `npm run build` succeeds in the canonical checkout.

Definition of Done:
- Anyone following this plan can run the workflow without wondering which local folder is “the real site repo”.

Status: Done.

Update (2026-02-23): In practice, we are already using `C:\Users\jirai\Documents\Projects\theproductwheel` as the canonical managed-site checkout during PR delivery.

---

### Milestone 7 — LLM Editorial Required (Quality Parity) (Approval Required)

Objective: Factory must use AI agents for editorial quality so manual-import posts match the “good post” standard (longer rewritten intro, human pick bodies, non-templated voice).

Deliverables:
- Editorial pass is mandatory for manual-import runs:
  - If OpenAI/LLM can’t run, the pipeline fails (no silent fallback to generic deterministic copy).
- Editorial rewrites:
  - Intro: uses seed_description as inspiration only (no copy-paste).
  - How chosen: practical bullet list similar in depth to the luggage post.
  - Pick bodies: generated for every pick and written in a varied, human style.
- Editorial constraints:
  - Do not imply hands-on testing.
  - Do not repeat rating/review counts in pick bodies (UI already displays them).
  - Keep required structural contracts intact (e.g., Topic extraction / validation constraints).

Acceptance criteria:
- A manual-import run with `OPENAI_API_KEY` produces:
  - A longer intro (2+ paragraphs), not the seed text verbatim.
  - Pick bodies that do not all read the same and include a clear “Skip it if…” line.
- A manual-import run without `OPENAI_API_KEY` fails clearly with an actionable error message.

Definition of Done:
- Factory output for a manual-import post resembles the luggage post style and passes validation/CI consistently.

Status: Done.

---

### Milestone 8 — Managed-Site Rendering Style Match (No “Closing”, Better Bodies) (Approval Required)

Objective: Align delivered markdown/body structure with what renders well on the managed site (hero + intro + picks), matching the luggage post’s user experience.

Deliverables:
- Remove the “Closing” section header from generated markdown body:
  - Affiliate disclosure should be a final paragraph without a heading, or handled by site layout.
- Ensure seed_description is not pasted verbatim:
  - It can inform tone and context, but the intro should be newly written.
- Ensure picks display like the luggage post:
  - Each pick body is two-part: why it’s included + “Skip it if…”.
  - Pick bodies are varied (avoid formulaic repetition).

Acceptance criteria:
- The delivered post page reads like the luggage post: hero + substantive intro + picks; no awkward “Closing” section.

Definition of Done:
- A regenerated manual-import post preview reads and renders with the same structure/tone pattern as the “good post”.

Status: Next.

---

### Milestone 9 — Quality Gates + Regression Tests (Approval Required)

Objective: Ensure we don’t regress back to “generic deterministic copy” or silently skipping AI agents.

Context (why tests previously passed without “AI agents”): historically, the factory pipeline could produce valid, schema-compliant artifacts entirely via deterministic generation, and the LLM editorial pass was best-effort (often skipped in environments without `OPENAI_API_KEY`). The unit tests primarily asserted structural/contract validity, not that editorial actually ran or that copy matched the “good post” style. Milestone 9 adds explicit mechanical gates for “editorial ran + style invariants”.

Deliverables:
- Add automated checks/tests to enforce:
  - Editorial step is required for manual-import flows (fails if not run).
  - No “## Closing” section header in output.
  - Pick bodies do not include rating/review strings (heuristic is OK).
  - Pick bodies contain a “Skip it if…” paragraph (or equivalent).
  - Required structural contracts remain intact after editorial.
- Add a test-friendly mode:
  - CI validates editorial output shape without network calls (stub/fake LLM output or fixture mode).

Acceptance criteria:
- CI fails if AI editorial is skipped or output violates the style/contract requirements.

Definition of Done:
- Quality parity is enforced mechanically; future posts keep the “good post” style by default.

Status: In Progress.

## Work Rules

- Do not begin a milestone until it is explicitly approved.
- If contract gaps appear, stop and revise Milestone 0 artifacts before continuing.
- Prefer minimal, contract-driven changes over one-off fixes.
