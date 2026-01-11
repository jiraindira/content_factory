from __future__ import annotations

import os
from typing import Any, Optional

from agents.base import BaseAgent
from agents.llm_client import LLMClient
from schemas.depth import (
    AppliedModule,
    DepthExpansionInput,
    DepthExpansionOutput,
    ExpansionModuleSpec,
    RewriteMode,
)
from styles.site_style import get_style_profile


def estimate_word_count(text: str) -> int:
    return len((text or "").strip().split())


def normalize_ws(text: str) -> str:
    return "\n".join([line.rstrip() for line in (text or "").splitlines()]).strip() + "\n"


def clamp_words(text: str, max_words: int) -> str:
    words = (text or "").split()
    if max_words <= 0 or len(words) <= max_words:
        return (text or "").strip()
    return " ".join(words[:max_words]).strip() + "…"


def has_section(markdown: str, heading: str) -> bool:
    return f"## {heading}".strip() in (markdown or "")


def append_section(markdown: str, new_section_md: str) -> str:
    md = markdown or ""
    if not md.endswith("\n"):
        md += "\n"
    return md + "\n" + new_section_md.strip() + "\n"


def insert_section_after(markdown: str, after_heading: str, new_section_md: str) -> str:
    md = markdown or ""
    after = f"## {after_heading}"
    if after not in md:
        return append_section(md, new_section_md)

    idx = md.find(after)
    if idx == -1:
        return append_section(md, new_section_md)

    next_idx = md.find("\n## ", idx + len(after))
    if next_idx == -1:
        if not md.endswith("\n"):
            md += "\n"
        return md + "\n" + new_section_md.strip() + "\n"

    before = md[:next_idx].rstrip() + "\n\n"
    after_part = md[next_idx:].lstrip("\n")
    return before + new_section_md.strip() + "\n\n" + after_part


def render_h2(heading: str, body: str) -> str:
    return f"## {heading}\n\n{body.strip()}\n"


def _contains_any(text: str, terms: list[str]) -> bool:
    t = (text or "").lower()
    return any(term.lower() in t for term in terms if term and term.strip())


def _sanitize_text(text: str, banned_phrases: list[str]) -> str:
    out = text or ""
    low = out.lower()
    for bp in banned_phrases or []:
        bpl = (bp or "").lower().strip()
        if not bpl:
            continue
        if bpl in low:
            out = out.replace(bp, "").replace(bp.title(), "").replace(bp.upper(), "")
            low = out.lower()
    return " ".join(out.split()).strip()


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class DepthExpansionAgent(BaseAgent):
    """
    DepthExpansionAgent (refactored into 2 passes)

    PASS 1: AUTHORING (per-section)
      - Writes/re-writes each module section body.
      - In upgrade mode, uses LLM for authoring.
      - In repair/preserve, uses deterministic profile fallbacks.

    PASS 2: EDITING (whole-doc)
      - Optional LLM sweep to improve flow/formatting/voice consistency.
      - Preserves YAML frontmatter, the products JSON, and all URLs.
      - Does not add testing claims.
      - Controlled by env DEPTH_ENABLE_EDIT_PASS (default: on).
    """

    name = "depth-expansion"

    def __init__(self) -> None:
        self.llm = LLMClient()

    def run(self, input: DepthExpansionInput | dict) -> dict[str, Any]:
        inp = input if isinstance(input, DepthExpansionInput) else DepthExpansionInput(**input)

        category = self._infer_category_from_draft(inp)
        profile = get_style_profile(category=category, voice=inp.voice)

        before_wc = estimate_word_count(inp.draft_markdown)
        expanded = normalize_ws(inp.draft_markdown)

        applied: list[AppliedModule] = []

        # -------------------------
        # PASS 1: AUTHORING
        # -------------------------
        for module in inp.modules:
            if not module.enabled:
                continue

            mode: RewriteMode = module.rewrite_mode or inp.rewrite_mode
            expanded_before = expanded

            if module.name == "why_this_list":
                expanded, meta = self._apply_why_this_list(inp, expanded, module, profile, mode)
            elif module.name == "quick_picks":
                expanded, meta = self._apply_quick_picks(inp, expanded, module, profile, mode)
            elif module.name == "how_we_chose":
                expanded, meta = self._apply_how_we_chose(inp, expanded, module, profile, mode)
            elif module.name == "buyers_guide":
                expanded, meta = self._apply_buyers_guide(inp, expanded, module, profile, mode)
            elif module.name == "faqs":
                expanded, meta = self._apply_faqs(inp, expanded, module, profile, mode)
            elif module.name == "alternatives":
                expanded, meta = self._apply_alternatives(inp, expanded, module, profile, mode)
            elif module.name == "care_and_maintenance":
                expanded, meta = self._apply_care_and_maintenance(inp, expanded, module, profile, mode)
            else:
                continue

            added_est = max(0, estimate_word_count(expanded) - estimate_word_count(expanded_before))
            applied.append(
                AppliedModule(
                    name=module.name,
                    added_words_estimate=int(meta.get("added_words_estimate", added_est)),
                    notes=str(meta.get("notes", "") or ""),
                )
            )

            if (estimate_word_count(expanded) - before_wc) >= inp.max_added_words:
                break

        # -------------------------
        # PASS 2: EDITING (optional)
        # -------------------------
        enable_edit_pass = _env_flag("DEPTH_ENABLE_EDIT_PASS", default=True)

        # Only run edit pass when we're explicitly in upgrade mode, because it’s a "voice + flow" editor.
        # Also avoid running if we already hit max_added_words.
        added_so_far = estimate_word_count(expanded) - before_wc
        if enable_edit_pass and inp.rewrite_mode == "upgrade" and added_so_far < inp.max_added_words:
            edited = self._edit_pass(inp=inp, md=expanded, profile=profile, category=category)
            # Guard against accidental length bloat:
            if estimate_word_count(edited) - before_wc <= inp.max_added_words:
                if edited.strip() != expanded.strip():
                    expanded = normalize_ws(edited)
                    applied.append(
                        AppliedModule(
                            name="edit_pass",
                            added_words_estimate=max(
                                0, estimate_word_count(expanded) - estimate_word_count(expanded_before)
                            ),
                            notes="Applied whole-document editor pass (upgrade).",
                        )
                    )

        after_wc = estimate_word_count(expanded)

        out = DepthExpansionOutput(
            expanded_markdown=expanded.strip() + "\n",
            applied_modules=applied,
            word_count_before=before_wc,
            word_count_after=after_wc,
        )
        return out.to_dict()

    # -------------------------
    # Category inference
    # -------------------------

    def _infer_category_from_draft(self, inp: DepthExpansionInput) -> str:
        md = inp.draft_markdown or ""
        marker = 'category: "'
        if marker in md:
            start = md.find(marker) + len(marker)
            end = md.find('"', start)
            if end != -1:
                val = md[start:end].strip()
                return val or "general"
        return "general"

    # -------------------------
    # Section extraction/replace
    # -------------------------

    def _extract_h2_body(self, md: str, heading: str) -> str:
        marker = f"## {heading}"
        if marker not in md:
            return ""
        start = md.find(marker)
        body_start = start + len(marker)
        next_start = md.find("\n## ", body_start)
        if next_start == -1:
            return md[body_start:].strip()
        return md[body_start:next_start].strip()

    def _replace_h2_section(self, md: str, heading: str, new_section_md: str) -> str:
        marker = f"## {heading}"
        if marker not in md:
            return md
        start = md.find(marker)
        next_start = md.find("\n## ", start + len(marker))
        if next_start == -1:
            return md[:start].rstrip() + "\n\n" + new_section_md.strip() + "\n"
        return md[:start].rstrip() + "\n\n" + new_section_md.strip() + "\n\n" + md[next_start:].lstrip("\n")

    # -------------------------
    # Rewrite decision
    # -------------------------

    def _should_rewrite_existing(self, md: str, heading: str, mode: RewriteMode) -> bool:
        if mode == "preserve":
            return False
        if mode == "upgrade":
            return True

        agent_markers = [
            "category rotation",
            "affiliate",
            "commercial intent",
            "saturated",
            "strong affiliate market",
            "fits category rotation",
            "audience:",
            "rationale:",
        ]
        boilerplate_markers = [
            "reduce regret",
            "feature-rich",
            "manufacturer instructions",
        ]
        section_text = self._extract_h2_body(md, heading)
        return _contains_any(section_text, agent_markers) or _contains_any(section_text, boilerplate_markers)

    # -------------------------
    # PASS 1: AUTHORING helpers
    # -------------------------

    def _llm_author_section(
        self,
        *,
        heading: str,
        category: str,
        profile: dict,
        inp: DepthExpansionInput,
        module: ExpansionModuleSpec,
        existing_text: str,
        intent: str,
        format_hint: str = "",
    ) -> str:
        banned = profile.get("banned_phrases", []) or []
        forbidden = profile.get("forbidden_terms", []) or []
        preferred = profile.get("preferred_terms", []) or []
        golden = (profile.get("golden_post_excerpt") or "").strip()

        products = inp.products or []
        product_bullets = "\n".join([f"- {p.get('title','')}: {p.get('description','')}" for p in products[:6]])

        system = (
            "You are writing a blog buying guide section in a personal, journal-like voice. "
            "Sound like a real person who has done too much scrolling and wants to save the reader time. "
            "Avoid corporate SEO tone."
        )

        user = f"""
Write the section body for: "{heading}"

CATEGORY: {category}

INTENT:
{intent}

STYLE REFERENCE (do NOT copy verbatim, just match the vibe):
{golden if golden else "(none)"}

CONSTRAINTS:
- Relatable, lightly witty, specific.
- No hype. No “best ever”. No exaggerated promises.
- Do NOT claim hands-on testing.
- Keep it skimmable and human.
- Output ONLY the section body text (no heading).
- Max about {module.max_words} words.

BANNED PHRASES (avoid):
{", ".join(banned) if banned else "(none)"}

FORBIDDEN TERMS (do not include):
{", ".join(forbidden) if forbidden else "(none)"}

PREFERRED TERMS (use only if natural):
{", ".join(preferred) if preferred else "(none)"}

EXISTING TEXT (rewrite/improve if present):
{existing_text.strip() if existing_text.strip() else "(none)"}

PRODUCT CONTEXT (don’t list them all unless asked):
{product_bullets if product_bullets.strip() else "(no products provided)"}

{format_hint}
""".strip()

        text = self.llm.generate_text(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,  # will be ignored if model doesn't support
            seed=1337,        # will be ignored if SDK/model doesn't support
            reasoning_effort="low",
        )

        text = _sanitize_text(text, banned)
        text = clamp_words(text, module.max_words)
        return text.strip()

    # -------------------------
    # PASS 2: EDITING
    # -------------------------

    def _split_frontmatter(self, md: str) -> tuple[str, str]:
        """
        Returns (frontmatter, body). If no frontmatter, frontmatter="" and body=md.
        """
        text = md or ""
        stripped = text.lstrip()
        if not stripped.startswith("---"):
            return "", text

        # Find the closing frontmatter fence
        # We assume YAML frontmatter starts at top.
        start = text.find("---")
        end = text.find("\n---", start + 3)
        if end == -1:
            return "", text

        end2 = text.find("\n", end + 4)
        if end2 == -1:
            return "", text

        fm = text[: end2 + 1]
        body = text[end2 + 1 :]
        return fm, body

    def _edit_pass(self, *, inp: DepthExpansionInput, md: str, profile: dict, category: str) -> str:
        """
        Whole-document editor sweep.

        Hard constraints:
          - Preserve YAML frontmatter verbatim.
          - Preserve products JSON block verbatim (frontmatter already contains it).
          - Do NOT change URLs.
          - Keep existing H2 section headings (don’t rename them).
          - Do not add testing claims.
          - Keep output markdown.
        """
        banned = profile.get("banned_phrases", []) or []
        forbidden = profile.get("forbidden_terms", []) or []
        preferred = profile.get("preferred_terms", []) or []
        golden = (profile.get("golden_post_excerpt") or "").strip()

        frontmatter, body = self._split_frontmatter(md)

        # Editor is only allowed to touch the BODY.
        system = (
            "You are a sharp but kind editor. You polish blog posts to feel human and readable. "
            "You fix formatting, flow, and repetition without changing facts."
        )

        user = f"""
You are editing ONLY the markdown BODY of a blog post.

GOALS:
- Improve flow and readability.
- Make the voice feel consistently personal/journal-like.
- Fix awkward bullet formatting (ensure bullets are on separate lines).
- Reduce repetition and bland filler.
- Keep it skimmable.

HARD RULES (do not break these):
- DO NOT change YAML frontmatter (you won't see it).
- DO NOT change any URLs.
- DO NOT add claims of hands-on testing.
- DO NOT rename existing H2 headings (keep the same "## ..." headings).
- Do not invent product features.
- Output ONLY the edited markdown BODY (no frontmatter).

CATEGORY: {category}

STYLE REFERENCE (do NOT copy verbatim, just match vibe):
{golden if golden else "(none)"}

BANNED PHRASES (avoid):
{", ".join(banned) if banned else "(none)"}

FORBIDDEN TERMS (do not include):
{", ".join(forbidden) if forbidden else "(none)"}

PREFERRED TERMS (use only if natural):
{", ".join(preferred) if preferred else "(none)"}

MARKDOWN BODY TO EDIT:
{body.strip()}
""".strip()

        edited_body = self.llm.generate_text(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,  # tolerated client will drop if unsupported
            seed=1337,
            reasoning_effort="low",
        )

        edited_body = _sanitize_text(edited_body, banned)
        edited_body = normalize_ws(edited_body)

        # Re-attach frontmatter exactly as-is
        if frontmatter:
            return frontmatter.rstrip() + "\n\n" + edited_body.lstrip("\n")
        return edited_body

    # -------------------------
    # Modules (AUTHORING)
    # -------------------------

    def _apply_why_this_list(self, inp, md, module, profile, mode):
        heading = "Why this list"
        category = self._infer_category_from_draft(inp)

        if has_section(md, heading):
            if not self._should_rewrite_existing(md, heading, mode):
                return md, {"added_words_estimate": 0, "notes": f"{heading} present; rewrite skipped ({mode})."}

            existing = self._extract_h2_body(md, heading)
            body = (
                self._llm_author_section(
                    heading=heading,
                    category=category,
                    profile=profile,
                    inp=inp,
                    module=module,
                    existing_text=existing,
                    intent="Set the scene for why this guide exists. Make it personal and relatable. 1–3 short paragraphs.",
                )
                if mode == "upgrade"
                else profile.get("why_this_list_body", "")
            )
            body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
            new_md = self._replace_h2_section(md, heading, render_h2(heading, body))
            return new_md, {
                "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
                "notes": f"Rewrote {heading} ({mode}).",
            }

        body = (
            self._llm_author_section(
                heading=heading,
                category=category,
                profile=profile,
                inp=inp,
                module=module,
                existing_text="",
                intent="Set the scene for why this guide exists. Make it personal and relatable. 1–3 short paragraphs.",
            )
            if mode == "upgrade"
            else profile.get("why_this_list_body", "")
        )
        body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
        section = render_h2(heading, body)
        new_md = insert_section_after(md, "Why this list", section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": f"Added {heading} ({mode}).",
        }

    def _apply_how_we_chose(self, inp, md, module, profile, mode):
        heading = "How we chose"
        category = self._infer_category_from_draft(inp)
        format_hint = "FORMAT: 1 short intro paragraph, then 4–6 bullet points."

        if has_section(md, heading):
            if not self._should_rewrite_existing(md, heading, mode):
                return md, {"added_words_estimate": 0, "notes": f"{heading} present; rewrite skipped ({mode})."}

            existing = self._extract_h2_body(md, heading)
            body = (
                self._llm_author_section(
                    heading=heading,
                    category=category,
                    profile=profile,
                    inp=inp,
                    module=module,
                    existing_text=existing,
                    intent="Explain selection criteria like a real person. Keep it practical and specific.",
                    format_hint=format_hint,
                )
                if mode == "upgrade"
                else self._render_how_we_chose_body(inp, module, profile)
            )
            body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
            new_md = self._replace_h2_section(md, heading, render_h2(heading, body))
            return new_md, {
                "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
                "notes": f"Rewrote {heading} ({mode}).",
            }

        body = (
            self._llm_author_section(
                heading=heading,
                category=category,
                profile=profile,
                inp=inp,
                module=module,
                existing_text="",
                intent="Explain selection criteria like a real person. Keep it practical and specific.",
                format_hint=format_hint,
            )
            if mode == "upgrade"
            else self._render_how_we_chose_body(inp, module, profile)
        )
        body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
        section = render_h2(heading, body)
        new_md = insert_section_after(md, "Why this list", section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": f"Added {heading} ({mode}).",
        }

    def _render_how_we_chose_body(self, inp, module, profile) -> str:
        intro = (profile.get("how_we_chose_intro") or "").strip()
        bullets = profile.get("how_we_chose_bullets", []) or []

        note = ""
        if inp.forbid_claims_of_testing:
            note = (
                "\n\n*Note: These recommendations are based on product details, broad review patterns, and common "
                "buyer criteria (not hands-on testing).*"
            )

        body = intro + "\n\n" + "\n".join([f"- {b}" for b in bullets]) + note
        body = _sanitize_text(body, profile.get("banned_phrases", []))
        return clamp_words(body, module.max_words)

    def _apply_quick_picks(self, inp, md, module, profile, mode):
        heading = "Quick picks"
        if has_section(md, heading):
            return md, {"added_words_estimate": 0, "notes": f"{heading} present; skipped."}

        prods = list(inp.products or [])
        if not prods:
            return md, {"added_words_estimate": 0, "notes": "No products provided; skipped quick picks."}

        intro_lines = profile.get("quick_picks_intro_lines", []) or []
        lines = [ln for ln in intro_lines if (ln or "").strip()]

        for p in prods[:6]:
            title = (p.get("title") or "").strip() or "A useful pick"
            desc = (p.get("description") or "").strip()
            one = desc.split(".")[0].strip() if desc else "A practical pick that’s easy to use and easy to keep."
            lines.append(f"- **{title}:** {one}")

        body = clamp_words(_sanitize_text("\n".join(lines).strip(), profile.get("banned_phrases", [])), module.max_words)
        section = render_h2(heading, body)
        new_md = insert_section_after(md, "How we chose" if has_section(md, "How we chose") else "Why this list", section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": f"Added {heading}.",
        }

    def _apply_buyers_guide(self, inp, md, module, profile, mode):
        heading = "Buyer’s guide"
        category = self._infer_category_from_draft(inp)
        format_hint = "FORMAT: 1 short intro sentence, then 5–7 bullet questions."

        if has_section(md, heading):
            if not self._should_rewrite_existing(md, heading, mode):
                return md, {"added_words_estimate": 0, "notes": f"{heading} present; rewrite skipped ({mode})."}

            existing = self._extract_h2_body(md, heading)
            body = (
                self._llm_author_section(
                    heading=heading,
                    category=category,
                    profile=profile,
                    inp=inp,
                    module=module,
                    existing_text=existing,
                    intent="Help the reader choose with practical questions that feel real.",
                    format_hint=format_hint,
                )
                if mode == "upgrade"
                else self._render_buyers_guide_body(module, profile)
            )
            body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
            new_md = self._replace_h2_section(md, heading, render_h2(heading, body))
            return new_md, {
                "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
                "notes": f"Rewrote {heading} ({mode}).",
            }

        body = (
            self._llm_author_section(
                heading=heading,
                category=category,
                profile=profile,
                inp=inp,
                module=module,
                existing_text="",
                intent="Help the reader choose with practical questions that feel real.",
                format_hint=format_hint,
            )
            if mode == "upgrade"
            else self._render_buyers_guide_body(module, profile)
        )
        body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
        section = render_h2(heading, body)
        new_md = append_section(md, section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": f"Added {heading} ({mode}).",
        }

    def _render_buyers_guide_body(self, module, profile) -> str:
        intro = (profile.get("buyers_guide_intro") or "").strip()
        qs = list(profile.get("buyers_guide_questions", []) or [])[:8]
        lines = [intro, ""]
        lines.extend([f"- **{q}**" for q in qs])
        body = _sanitize_text("\n".join(lines).strip(), profile.get("banned_phrases", []))
        return clamp_words(body, module.max_words)

    def _apply_faqs(self, inp, md, module, profile, mode):
        heading = "FAQs"
        category = self._infer_category_from_draft(inp)
        format_hint = "FORMAT: 3–5 Q&As. Each question bolded. Answers 1–3 sentences."

        if has_section(md, heading):
            if not self._should_rewrite_existing(md, heading, mode):
                return md, {"added_words_estimate": 0, "notes": f"{heading} present; rewrite skipped ({mode})."}

            existing = self._extract_h2_body(md, heading)
            body = (
                self._llm_author_section(
                    heading=heading,
                    category=category,
                    profile=profile,
                    inp=inp,
                    module=module,
                    existing_text=existing,
                    intent="Write FAQs that are short, helpful, and grounded. No wild claims.",
                    format_hint=format_hint,
                )
                if mode == "upgrade"
                else self._render_faqs_body(inp, module, profile)
            )
            body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
            new_md = self._replace_h2_section(md, heading, render_h2(heading, body))
            return new_md, {
                "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
                "notes": f"Rewrote {heading} ({mode}).",
            }

        body = (
            self._llm_author_section(
                heading=heading,
                category=category,
                profile=profile,
                inp=inp,
                module=module,
                existing_text="",
                intent="Write FAQs that are short, helpful, and grounded. No wild claims.",
                format_hint=format_hint,
            )
            if mode == "upgrade"
            else self._render_faqs_body(inp, module, profile)
        )
        body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
        section = render_h2(heading, body)
        new_md = append_section(md, section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": f"Added {heading} ({mode}).",
        }

    def _render_faqs_body(self, inp, module, profile) -> str:
        faqs = [q.strip() for q in (inp.faqs or []) if q and q.strip()]
        if not faqs:
            faqs = list(profile.get("faq_seeds", []) or [])[:6]

        answers = profile.get("faq_answers", {}) or {}
        default_answer = (profile.get("faq_default_answer") or "").strip()

        blocks: list[str] = []
        intro = (profile.get("faq_intro") or "").strip()
        if intro:
            blocks.append(intro)
            blocks.append("")

        for q in faqs[:6]:
            a = answers.get(q, default_answer)
            blocks.append(f"**{q}**\n\n{a}\n")

        body = _sanitize_text("\n".join(blocks).strip(), profile.get("banned_phrases", []))
        return clamp_words(body, module.max_words)

    def _apply_alternatives(self, inp, md, module, profile, mode):
        heading = "Alternatives worth considering"
        category = self._infer_category_from_draft(inp)
        format_hint = "FORMAT: 1 short intro, then 3–6 bullets."

        if has_section(md, heading):
            if not self._should_rewrite_existing(md, heading, mode):
                return md, {"added_words_estimate": 0, "notes": f"{heading} present; rewrite skipped ({mode})."}

            existing = self._extract_h2_body(md, heading)
            body = (
                self._llm_author_section(
                    heading=heading,
                    category=category,
                    profile=profile,
                    inp=inp,
                    module=module,
                    existing_text=existing,
                    intent="Suggest alternative angles (budget, premium, smaller, simpler) with concrete reasons.",
                    format_hint=format_hint,
                )
                if mode == "upgrade"
                else self._render_alternatives_body(module, profile)
            )
            body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
            new_md = self._replace_h2_section(md, heading, render_h2(heading, body))
            return new_md, {
                "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
                "notes": f"Rewrote {heading} ({mode}).",
            }

        body = (
            self._llm_author_section(
                heading=heading,
                category=category,
                profile=profile,
                inp=inp,
                module=module,
                existing_text="",
                intent="Suggest alternative angles (budget, premium, smaller, simpler) with concrete reasons.",
                format_hint=format_hint,
            )
            if mode == "upgrade"
            else self._render_alternatives_body(module, profile)
        )
        body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
        section = render_h2(heading, body)
        new_md = append_section(md, section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": f"Added {heading} ({mode}).",
        }

    def _render_alternatives_body(self, module, profile) -> str:
        intro = (profile.get("alternatives_intro") or "").strip()
        tips = list(profile.get("alternatives_tips", []) or [])[:8]
        lines: list[str] = []
        if intro:
            lines.append(intro)
            lines.append("")
        lines.extend([f"- {t}" for t in tips])
        body = _sanitize_text("\n".join(lines).strip(), profile.get("banned_phrases", []))
        return clamp_words(body, module.max_words)

    def _apply_care_and_maintenance(self, inp, md, module, profile, mode):
        heading = "Care and maintenance"
        category = self._infer_category_from_draft(inp)
        format_hint = "FORMAT: 1 short intro, then 4–7 bullets. Be practical."

        if has_section(md, heading):
            if not self._should_rewrite_existing(md, heading, mode):
                return md, {"added_words_estimate": 0, "notes": f"{heading} present; rewrite skipped ({mode})."}

            existing = self._extract_h2_body(md, heading)
            body = (
                self._llm_author_section(
                    heading=heading,
                    category=category,
                    profile=profile,
                    inp=inp,
                    module=module,
                    existing_text=existing,
                    intent="Give practical care tips (cleaning, storage, common mistakes, returns).",
                    format_hint=format_hint,
                )
                if mode == "upgrade"
                else self._render_care_body(module, profile)
            )
            body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
            new_md = self._replace_h2_section(md, heading, render_h2(heading, body))
            return new_md, {
                "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
                "notes": f"Rewrote {heading} ({mode}).",
            }

        body = (
            self._llm_author_section(
                heading=heading,
                category=category,
                profile=profile,
                inp=inp,
                module=module,
                existing_text="",
                intent="Give practical care tips (cleaning, storage, common mistakes, returns).",
                format_hint=format_hint,
            )
            if mode == "upgrade"
            else self._render_care_body(module, profile)
        )
        body = clamp_words(_sanitize_text(body, profile.get("banned_phrases", [])), module.max_words)
        section = render_h2(heading, body)
        new_md = append_section(md, section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": f"Added {heading} ({mode}).",
        }

    def _render_care_body(self, module, profile) -> str:
        intro = (profile.get("care_intro") or "").strip()
        tips = list(profile.get("care_tips", []) or [])[:10]
        lines: list[str] = []
        if intro:
            lines.append(intro)
            lines.append("")
        lines.extend([f"- {t}" for t in tips])
        body = _sanitize_text("\n".join(lines).strip(), profile.get("banned_phrases", []))
        return clamp_words(body, module.max_words)
