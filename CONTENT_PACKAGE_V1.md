# Content Package v1 (Factory → Managed Site Contract)

Date: 2026-02-16

## Purpose

This document defines the **stable handoff contract** between:

- **Content Factory** (generation): produces a reviewable “content-only” package.
- **Managed Site** (publishing): hydrates assets (hero + pick images), writes into the Astro repo, and prepares a mergeable PR.

This contract is **brand-agnostic**, but must support TheProductWheel as the first managed-site integration.

## Package Semantics

- A package represents one publishable unit: **one blog post**.
- The package is **content-only**:
  - It may include product URLs and structured pick/product metadata.
  - It must not include downloaded images.
- The managed site is responsible for **asset hydration**:
  - pick thumbnails (download/optimize + write frontmatter `products[].image`)
  - hero images (generate/select + reference in frontmatter)

## Directory Layout

A package is a directory:

- `packages/{brand_id}/{run_id}/`
  - `manifest.json`
  - `post.md`

`run_id` is an opaque unique identifier (timestamp/uuid).

## Manifest Schema (v1)

`manifest.json` fields:

- `version`: string, must be `"1"`
- `brand_id`: string (e.g. `"the_product_wheel"`)
- `run_id`: string
- `created_at`: ISO-8601 string
- `publish_date`: `YYYY-MM-DD`
- `slug`: string (kebab-case; no date prefix)
- `outputs`: array of objects:
  - `kind`: currently only `"blog_post"`
  - `path`: currently only `"post.md"`

## Blog Post File (post.md)

`post.md` is Markdown with **Astro-compatible frontmatter**.

### Required frontmatter keys (v1)

These are the **minimum** required keys to render correctly in the managed site:

- `title`: string
- `description`: string
- `publishedAt`: ISO-8601 string or date-like string (Astro schema coerces to Date)
- `categories`: string[] (must map to managed-site taxonomy)
- `products`: array (drives pick cards and sidebar)
  - Each product entry must contain:
    - `pick_id`: string
    - `title`: string
    - `url`: string (fully-qualified http(s), or empty string)
  - Optional (managed-site hydration may fill):
    - `image`: string (absolute URL or site-root path like `/images/...`)
- `picks`: optional array (metadata the managed site can use)
  - Each pick entry:
    - `pick_id`: string
    - `body`: string

Notes:
- In this repo, the managed site prefers `picks[]` in frontmatter, but can fall back to parsing a `## The picks` section.
- v1 expects factory outputs to include `picks[]` when possible (at minimum: `pick_id` + `body`).

### Body conventions

- Content should be written for human reading.
- No embedded local image paths are required in v1.
- If affiliate links are used, the URLs must already be in final form (managed site should not need to rewrite them in v1).

## Slug Rules

- `slug` is kebab-case, derived from title, and must be stable.
- The managed site chooses the final on-disk filename, typically:
  - `YYYY-MM-DD-{slug}.md`

## Validation Responsibilities

Factory validates:
- manifest schema
- required frontmatter keys exist and types are correct
- URLs are well-formed
- categories are present (not necessarily verified against site taxonomy in v1)

Managed site validates:
- taxonomy/category mapping against its own `taxonomy.json`
- hero + pick images exist locally after hydration
- Astro build/content-collection validation

## Versioning

- The manifest field `version` is the contract selector.
- Breaking changes require bumping version and parallel support during migration.
