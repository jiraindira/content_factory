# Legacy Agents Audit (Bias / Reuse)

This document classifies the legacy `agents/` + `pipeline/` components by whether they are:

- **Reusable / neutral**: can be used across intents/channels with minimal changes
- **Product/blog-specific**: assumes “buying guide” structure or product-list content

The goal is to prevent product/affiliate assumptions from leaking into thought leadership, email, or LinkedIn outputs.

## Summary

### Product/blog-specific (biased)

- `ProductDiscoveryAgent` (agents/product_agent.py)
  - Hard-coded to “affiliate marketer” and “Amazon-relevant” discovery.
- `PreflightQAAgent` (agents/preflight_qa_agent.py)
  - Enforces “picks” parsing and product-count rules (`## The picks`, `pick_id` markers, "Skip it if" guidance).
- `PostRepairAgent` (agents/post_repair_agent.py)
  - Repairs are coupled to the picks contract (e.g., inserting "Skip it if" per pick).
- `pipeline/manual_post_writer.py`
  - Writes Astro blog posts with product sections/hero/frontmatter expectations.

### Mostly reusable (with guardrails)

- `FinalTitleAgent` (agents/final_title_agent.py)
  - General title formatting; should receive constraints from context.
- `TitleOptimizationAgent` (agents/title_optimization_agent.py)
  - Good anti-clickbait heuristics, but includes buying-guide phrase bans which may not apply to all intents.
- `DepthExpansionAgent` (agents/depth_expansion_agent.py)
  - Formatting cleanup; should be used only where the output format matches its assumptions.

## Required architectural change

- Do **not** attempt to make all legacy agents universal.
- Add a deterministic **router** that selects an agent set based on validated `intent/form/channel`.
- Ensure thought leadership paths never execute product/blog-specific QA/repair rules.

## Milestone 7 implementation approach

- Implement intent/form routing and intent-specific generation in `content_factory/`.
- Keep the legacy affiliate engine intact, but treat it as one specialized pipeline.
