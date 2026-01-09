from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from schemas.depth import (
    AppliedModule,
    DepthExpansionInput,
    DepthExpansionOutput,
    ExpansionModuleSpec,
)


def estimate_word_count(text: str) -> int:
    return len((text or "").strip().split())


def normalize_ws(text: str) -> str:
    return "\n".join([line.rstrip() for line in (text or "").splitlines()]).strip() + "\n"


def clamp_words(text: str, max_words: int) -> str:
    """
    Best-effort word clamp. Deterministic.
    Preserves paragraph breaks but truncates at word boundary.
    """
    words = (text or "").split()
    if max_words <= 0 or len(words) <= max_words:
        return (text or "").strip()
    return " ".join(words[:max_words]).strip() + "…"


def has_section(markdown: str, heading: str) -> bool:
    """
    Checks for a markdown H2 section "## {heading}".
    """
    needle = f"## {heading}".strip()
    return needle in (markdown or "")


def insert_section_after(markdown: str, after_heading: str, new_section_md: str) -> str:
    """
    Insert `new_section_md` after the first occurrence of "## {after_heading}" section block.
    If not found, append at end.

    Deterministic and simple. Does not parse full markdown AST.
    """
    md = markdown or ""
    after = f"## {after_heading}"
    if after not in md:
        return append_section(md, new_section_md)

    # Find insertion point: end of the after section content (until next H2 or EOF)
    idx = md.find(after)
    if idx == -1:
        return append_section(md, new_section_md)

    # Locate start of next H2 heading after idx
    next_idx = md.find("\n## ", idx + len(after))
    if next_idx == -1:
        # No next section; append at end
        if not md.endswith("\n"):
            md += "\n"
        return md + "\n" + new_section_md.strip() + "\n"

    # Insert before next section
    before = md[:next_idx].rstrip() + "\n\n"
    after_part = md[next_idx:].lstrip("\n")
    return before + new_section_md.strip() + "\n\n" + after_part


def append_section(markdown: str, new_section_md: str) -> str:
    md = markdown or ""
    if not md.endswith("\n"):
        md += "\n"
    return md + "\n" + new_section_md.strip() + "\n"


def render_h2(heading: str, body: str) -> str:
    return f"## {heading}\n\n{body.strip()}\n"


def _safe_products(inp: DepthExpansionInput) -> list[dict]:
    # Ensure deterministic ordering for any downstream rendering.
    # Assumes products already sorted upstream, but enforce stable order anyway.
    prods = list(inp.products or [])
    # If fields missing, fallback to empty. Sort by rating then reviews if present.
    def key(p: dict) -> tuple:
        return (
            float(p.get("rating", 0) or 0),
            int(p.get("reviews_count", 0) or 0),
            str(p.get("title", "") or ""),
        )

    return sorted(prods, key=key, reverse=True)


def _categorize_product(p: dict) -> str:
    """
    Very lightweight product category inference from title/description.
    Deterministic keyword matching.
    """
    t = f"{p.get('title','')} {p.get('description','')}".lower()

    if any(k in t for k in ["airpods", "earbud", "earbuds", "in-ear", "in ear"]):
        return "earbuds"
    if any(k in t for k in ["headphones", "noise cancel", "noise-cancel", "wh-"]):
        return "headphones"
    if any(k in t for k in ["echo show", "alexa", "smart display", "smart home"]):
        return "smart_display"
    if any(k in t for k in ["fitbit", "tracker", "fitness", "health", "heart rate", "sleep"]):
        return "fitness_tracker"
    if any(k in t for k in ["kindle", "ereader", "e-reader", "paperwhite"]):
        return "ereader"
    if any(k in t for k in ["power bank", "powerbank", "battery pack", "powercore", "anker"]):
        return "power_bank"
    if any(k in t for k in ["drone", "dji", "aerial"]):
        return "drone"
    if any(k in t for k in ["phone", "smartphone", "galaxy", "iphone", "pixel", "fold", "flip"]):
        return "phone"

    return "tech_gadget"


def _voice_nudge(voice: str) -> dict[str, str]:
    """
    Small deterministic voice variations. Keep subtle.
    """
    v = (voice or "neutral").lower().strip()
    if v in {"wirecutterish", "wirecutter"}:
        return {
            "tone_open": "If you just want the short list, you’re in the right place.",
            "tone_close": "A good gift is one they’ll use in February, not just in December.",
        }
    if v in {"nerdwalletish", "nerdwallet"}:
        return {
            "tone_open": "We focused on value, usefulness, and avoiding buyer’s remorse.",
            "tone_close": "Aim for the option that fits their habits, not the one with the flashiest spec sheet.",
        }
    return {
        "tone_open": "We focused on gifts that are easy to love and easy to use.",
        "tone_close": "Pick the gift that fits their everyday life, not just the holiday moment.",
    }


class DepthExpansionAgent(BaseAgent):
    """
    Expands a draft markdown post by applying a set of expansion modules.

    IMPORTANT: Your Astro site renders product cards from frontmatter, so by default
    this agent avoids duplicating product lists in the body unless render_products_in_body=True.
    """

    name = "depth-expansion"

    def run(self, input: DepthExpansionInput | dict) -> dict[str, Any]:
        inp = input if isinstance(input, DepthExpansionInput) else DepthExpansionInput(**input)

        before_wc = estimate_word_count(inp.draft_markdown)
        expanded = normalize_ws(inp.draft_markdown)

        applied: list[AppliedModule] = []

        # Apply modules in order (best effort).
        for module in inp.modules:
            if not module.enabled:
                continue

            expanded_before = expanded
            if module.name == "quick_picks":
                expanded, meta = self._apply_quick_picks(inp, expanded, module)
            elif module.name == "how_we_chose":
                expanded, meta = self._apply_how_we_chose(inp, expanded, module)
            elif module.name == "buyers_guide":
                expanded, meta = self._apply_buyers_guide(inp, expanded, module)
            elif module.name == "faqs":
                expanded, meta = self._apply_faqs(inp, expanded, module)
            elif module.name == "alternatives":
                expanded, meta = self._apply_alternatives(inp, expanded, module)
            elif module.name == "care_and_maintenance":
                expanded, meta = self._apply_care_and_maintenance(inp, expanded, module)
            else:
                # Unknown module: deterministic no-op
                continue

            added_est = max(0, estimate_word_count(expanded) - estimate_word_count(expanded_before))
            applied.append(
                AppliedModule(
                    name=module.name,
                    added_words_estimate=int(meta.get("added_words_estimate", added_est)),
                    notes=str(meta.get("notes", "") or ""),
                )
            )

            # Stop if we hit max_added_words (best effort).
            if (estimate_word_count(expanded) - before_wc) >= inp.max_added_words:
                break

        after_wc = estimate_word_count(expanded)

        out = DepthExpansionOutput(
            expanded_markdown=expanded.strip() + "\n",
            applied_modules=applied,
            word_count_before=before_wc,
            word_count_after=after_wc,
        )
        return out.to_dict()

    # -------------------------
    # Module implementations
    # -------------------------

    def _apply_quick_picks(
        self, inp: DepthExpansionInput, md: str, module: ExpansionModuleSpec
    ) -> tuple[str, dict]:
        if has_section(md, "Quick picks"):
            return md, {"added_words_estimate": 0, "notes": "Quick picks already present; skipped."}

        prods = _safe_products(inp)
        if not prods:
            return md, {"added_words_estimate": 0, "notes": "No products provided; skipped quick picks."}

        # Take top 6 by rating/reviews ordering.
        top = prods[:6]
        vibe = _voice_nudge(inp.voice)

        lines: list[str] = []
        lines.append(vibe["tone_open"])
        lines.append("")
        for p in top:
            title = str(p.get("title", "")).strip() or "A solid pick"
            cat = _categorize_product(p)
            why = self._one_line_why(cat)
            lines.append(f"- **{title}:** {why}")

        body = clamp_words("\n".join(lines).strip(), module.max_words)
        section = render_h2("Quick picks", body)

        # Insert after "Why this list" if present; else append
        new_md = insert_section_after(md, "Why this list", section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": "Added a quick picks summary section.",
        }

    def _apply_how_we_chose(
        self, inp: DepthExpansionInput, md: str, module: ExpansionModuleSpec
    ) -> tuple[str, dict]:
        if has_section(md, "How we chose"):
            return md, {"added_words_estimate": 0, "notes": "How we chose already present; skipped."}

        vibe = _voice_nudge(inp.voice)
        bullets = [
            "**Low friction:** setup and daily use should be simple.",
            "**Real utility:** the best gifts solve a problem you actually have.",
            "**Compatibility:** ecosystem fit matters (Apple/Android, smart home platforms).",
            "**Value:** not just cheap, but worth the space it takes up.",
            "**Support:** returns and warranty are part of the product.",
        ]

        note = ""
        if inp.forbid_claims_of_testing:
            note = (
                "\n\n*Note: These recommendations are based on product details, broad review patterns, and buyer criteria "
                "(not hands-on testing).*"
            )

        body = "\n".join([vibe["tone_close"], "", *[f"- {b}" for b in bullets]]) + note
        body = clamp_words(body.strip(), module.max_words)

        section = render_h2("How we chose", body)
        new_md = insert_section_after(md, "Why this list", section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": "Added selection criteria and guardrail note.",
        }

    def _apply_buyers_guide(
        self, inp: DepthExpansionInput, md: str, module: ExpansionModuleSpec
    ) -> tuple[str, dict]:
        if has_section(md, "Buyer’s guide"):
            return md, {"added_words_estimate": 0, "notes": "Buyer’s guide already present; skipped."}

        pk = (inp.primary_keyword or inp.topic).strip()
        secondaries = [s.strip() for s in (inp.secondary_keywords or []) if s and s.strip()]
        prods = _safe_products(inp)
        cats = {_categorize_product(p) for p in prods[:10]} if prods else set()

        questions = [
            "**Where will they use it most?** Home, commute, gym, travel all point to different picks.",
            "**What ecosystem are they in?** Apple vs Android (and Alexa vs Google) can make or break the experience.",
            "**Do they like low-maintenance tech or hobby tech?** Some gifts are “set it and forget it,” others are a weekend project.",
            "**Is this a ‘wow’ gift or a ‘daily value’ gift?** Both are valid, but they land differently.",
        ]

        if "drone" in cats:
            questions.append("**Will they actually be able to use it?** Some products (like drones) come with local rules and learning curves.")

        if secondaries:
            questions.append(f"**Related considerations:** {', '.join(secondaries[:5])}.")

        body = (
            f"If you’re shopping for **{pk}** gifts, these questions usually get you to the right choice:\n\n"
            + "\n".join([f"- {q}" for q in questions])
        )
        body = clamp_words(body.strip(), module.max_words)

        section = render_h2("Buyer’s guide", body)
        new_md = append_section(md, section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": "Added a practical buyer’s guide section.",
        }

    def _apply_faqs(
        self, inp: DepthExpansionInput, md: str, module: ExpansionModuleSpec
    ) -> tuple[str, dict]:
        if has_section(md, "FAQs"):
            return md, {"added_words_estimate": 0, "notes": "FAQs already present; skipped."}

        # If no FAQs provided, generate a small deterministic set based on product categories.
        faqs = [q.strip() for q in (inp.faqs or []) if q and q.strip()]
        if not faqs:
            faqs = self._default_faqs_from_products(_safe_products(inp))

        if not faqs:
            return md, {"added_words_estimate": 0, "notes": "No FAQs available; skipped."}

        # Deterministic answers. No claims of hands-on testing.
        qa_blocks: list[str] = []
        for q in faqs[:8]:
            qa_blocks.append(f"**{q}**\n\n{self._answer_faq(inp, q)}\n")

        body = clamp_words("\n".join(qa_blocks).strip(), module.max_words)
        section = render_h2("FAQs", body)
        new_md = append_section(md, section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": f"Added FAQ section with {min(8, len(faqs))} questions.",
        }

    def _apply_alternatives(
        self, inp: DepthExpansionInput, md: str, module: ExpansionModuleSpec
    ) -> tuple[str, dict]:
        if has_section(md, "Alternatives worth considering"):
            return md, {"added_words_estimate": 0, "notes": "Alternatives already present; skipped."}

        prods = _safe_products(inp)
        cats = {_categorize_product(p) for p in prods[:12]} if prods else set()

        ideas: list[str] = []
        ideas.append("- **A lower-cost version** if you’re unsure they’ll use it often.")
        ideas.append("- **A higher-end pick** if durability, warranty, or comfort matters most.")
        ideas.append("- **A smaller/lighter option** if storage and portability are constraints.")

        if "headphones" in cats or "earbuds" in cats:
            ideas.append("- **Different audio style**: earbuds vs over-ear depends on comfort and where they’ll use it.")
        if "smart_display" in cats:
            ideas.append("- **A simple smart speaker + smart bulbs bundle** for an easy, fun intro to smart home.")
        if "fitness_tracker" in cats:
            ideas.append("- **A smartwatch** if they want notifications + apps, not just health metrics.")
        if "ereader" in cats:
            ideas.append("- **A basic e-reader** if you want the reading experience for less money.")
        if "drone" in cats:
            ideas.append("- **An action camera** if they want travel footage with less setup and fewer rules.")

        body = clamp_words("\n".join(ideas).strip(), module.max_words)
        section = render_h2("Alternatives worth considering", body)
        new_md = append_section(md, section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": "Added alternatives section tailored to detected product categories.",
        }

    def _apply_care_and_maintenance(
        self, inp: DepthExpansionInput, md: str, module: ExpansionModuleSpec
    ) -> tuple[str, dict]:
        if has_section(md, "Care and maintenance"):
            return md, {"added_words_estimate": 0, "notes": "Care and maintenance already present; skipped."}

        prods = _safe_products(inp)
        cats = {_categorize_product(p) for p in prods[:12]} if prods else set()

        tips: list[str] = []
        tips.append("- **Keep packaging until they’ve tried it** (returns are much easier).")
        tips.append("- **Avoid extreme heat** for anything with a battery.")
        tips.append("- **Use a case when it makes sense** (small protection, big payoff).")

        if "earbuds" in cats or "headphones" in cats:
            tips.append("- **Audio gear:** wipe ear tips/pads occasionally; store in a case to protect battery and reduce “where did it go?” moments.")
        if "ereader" in cats:
            tips.append("- **E-readers:** a simple cover prevents scratches; follow the device’s waterproof guidance even if it’s rated as water-resistant.")
        if "power_bank" in cats:
            tips.append("- **Power banks:** store at a moderate charge if unused for months; don’t leave them baking in a car.")
        if "drone" in cats:
            tips.append("- **Drones:** batteries and props are wear items; a travel case saves stress and time.")
        if "smart_display" in cats:
            tips.append("- **Smart displays:** place it where it’s genuinely useful (kitchen or entryway tends to beat a random shelf).")

        body = clamp_words("\n".join(tips).strip(), module.max_words)
        section = render_h2("Care and maintenance", body)
        new_md = append_section(md, section)
        return new_md, {
            "added_words_estimate": max(0, estimate_word_count(new_md) - estimate_word_count(md)),
            "notes": "Added care/maintenance tips tailored to detected product categories.",
        }

    # -------------------------
    # Deterministic helpers
    # -------------------------

    def _one_line_why(self, category: str) -> str:
        # Short, deterministic "why" lines used in Quick picks.
        mapping = {
            "earbuds": "Easy everyday audio, great for commutes and calls.",
            "headphones": "Premium comfort and noise cancellation for focus and travel.",
            "smart_display": "A shared screen for calendars, reminders, and home routines.",
            "fitness_tracker": "Health insights without the bulk of a full smartwatch.",
            "ereader": "A small device that makes reading more convenient everywhere.",
            "power_bank": "The gift of never hitting 3% at the worst moment.",
            "drone": "Big creative payoff if they’ll actually use it outdoors.",
            "phone": "High-impact upgrade, especially for the style-and-tech crowd.",
            "tech_gadget": "A useful upgrade that fits lots of lifestyles.",
        }
        return mapping.get(category, mapping["tech_gadget"])

    def _default_faqs_from_products(self, products: list[dict]) -> list[str]:
        cats = {_categorize_product(p) for p in products[:12]} if products else set()
        qs: list[str] = []

        qs.append("How do I pick the right tech gift if I’m not sure what they want?")
        if "earbuds" in cats or "headphones" in cats:
            qs.append("Are earbuds or over-ear headphones a better gift?")
            qs.append("Do noise-canceling headphones make a noticeable difference?")
        if "smart_display" in cats:
            qs.append("Is a smart display worth it if someone doesn’t have a smart home?")
        if "fitness_tracker" in cats:
            qs.append("Is a fitness tracker a risky gift?")
        if "ereader" in cats:
            qs.append("Is an e-reader still worth it if someone likes physical books?")
        if "drone" in cats:
            qs.append("Do drones have rules or restrictions?")
        if "power_bank" in cats:
            qs.append("What should I look for in a power bank gift?")

        return qs[:8]

    def _answer_faq(self, inp: DepthExpansionInput, question: str) -> str:
        q = (question or "").lower()

        if "pick the right tech gift" in q or "not sure" in q:
            return (
                "Start with where they’ll use it (home, commute, gym, travel), then check ecosystem fit "
                "(Apple/Android, Alexa/Google). If you’re still unsure, pick a practical “daily value” gift "
                "like charging gear, audio, or reading."
            )

        if "earbuds or over-ear" in q:
            return (
                "Earbuds are great for portability and quick use. Over-ear headphones are usually more comfortable "
                "for long sessions and often have stronger noise canceling. If they travel or work in noisy places, "
                "over-ear is a safer bet."
            )

        if "noise-cancel" in q or "noise cancel" in q:
            return (
                "For many people, yes. Noise canceling is most noticeable on steady background noise "
                "(planes, trains, offices). If they’re sensitive to sound or travel often, it’s one of the most "
                "giftable upgrades."
            )

        if "smart display" in q:
            return (
                "It’s still useful even without a full smart home if they’ll use it for calendars, reminders, "
                "kitchen timers, casual video calls, or quick media. If they dislike voice assistants or are privacy-sensitive, "
                "it’s less likely to land well."
            )

        if "fitness tracker" in q or "risky gift" in q:
            return (
                "It depends on your relationship and how it’s framed. It lands best as “helpful insight” "
                "(sleep, steps, heart rate) rather than “you should work out.” If they already have a preferred brand, "
                "match that ecosystem."
            )

        if "e-reader" in q or "physical books" in q:
            return (
                "Many book lovers still like an e-reader for travel, bedtime reading, and convenience. "
                "It doesn’t replace physical books; it complements them. If they truly only read print, "
                "a bookshop gift card may be the better move."
            )

        if "drones" in q or "rules" in q or "restrictions" in q:
            return (
                "Rules vary by country and even by city. If you’re gifting a drone to a traveler, it’s worth checking "
                "local regulations and no-fly zones. Also consider whether they’ll enjoy the learning curve."
            )

        if "power bank" in q:
            return (
                "Look for capacity (so it can actually recharge a phone), fast charging support, and the right ports "
                "for their devices. Bigger capacity usually means more weight, so choose based on how they travel."
            )

        # Default safe answer
        return (
            "A good rule is to prioritize compatibility, simplicity, and usefulness. The best tech gifts are the ones "
            "that quietly become part of someone’s routine."
        )
