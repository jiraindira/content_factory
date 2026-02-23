from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from integrations.openai_adapters import OpenAIJsonLLM


@dataclass(frozen=True)
class CopyEditorConfig:
    max_changes: int = 20
    max_pick_sentences: int = 4


class CopyEditorAgent:
    """Body-only copy editor.

    Edits narrative content ONLY:
      - Intro section markdown
      - How-this-list-was-chosen section markdown
      - picks[].body strings (treated as content, even if stored in frontmatter)

    Never edits metadata such as title, description, dates, categories, products, URLs, or images.
    """

    def __init__(self, *, llm: OpenAIJsonLLM, config: CopyEditorConfig | None = None) -> None:
        self._llm = llm
        self._cfg = config or CopyEditorConfig()

    def run(
        self,
        *,
        title: str,
        audience: str,
        intro_md: str,
        how_md: str,
        picks: list[dict[str, Any]],
        products: list[dict[str, Any]],
        category: str,
    ) -> dict[str, Any]:
        """Returns edited fragments.

        Shape:
          {
            "intro_md": "...",
            "how_md": "...",
            "picks": [{"pick_id": "...", "body": "..."}, ...],
            "changes_made": ["...", ...]
          }
        """

        products_min = []
        for p in products or []:
            if isinstance(p, dict):
                products_min.append(
                    {
                        "pick_id": str(p.get("pick_id") or "").strip(),
                        "title": str(p.get("title") or "").strip(),
                    }
                )

        picks_min = []
        for p in picks or []:
            if isinstance(p, dict):
                picks_min.append(
                    {
                        "pick_id": str(p.get("pick_id") or "").strip(),
                        "body": str(p.get("body") or ""),
                    }
                )

        system = (
            "You are the house copywriter + editor for a shopping guide.\n"
            "You MUST only write/edit narrative content (intro/how/pick bodies).\n"
            "Your goal is to make the post feel human and helpful, not templated.\n"
            "\n"
            "Allowed edits:\n"
            "- Rewrite and expand the intro into 2–3 short paragraphs (do not copy-paste the draft; use it as inspiration).\n"
            "- Rewrite/expand the 'how chosen' section into practical selection criteria as a Markdown bullet list (3–6 bullets).\n"
            "  - Each bullet MUST be on its own line and MUST start with '- ' (dash + space).\n"
            "  - Do NOT use the '•' bullet glyph.\n"
            "- For each pick, write a two-part body: (1) why it’s here / who it’s for, (2) exactly one sentence that starts with 'Skip it if'.\n"
            "- Vary phrasing across picks (do not reuse the same sentence templates).\n"
            "- You may use first-person phrasing sparingly (e.g., 'I like this pick because…'), but do NOT imply hands-on testing.\n"
            "- Fix typos, reduce repetition, improve clarity.\n"
            "\n"
            "Forbidden edits (never do these):\n"
            "- Do NOT change product titles, pick_id values, URLs, prices, ratings, or review counts.\n"
            "- Do NOT add specific specs, measurements, guarantees, certifications, or performance claims.\n"
            "- Do NOT claim hands-on testing or personal experience.\n"
            "- Do NOT mention rating numbers, star symbols, or review counts in pick bodies (the UI already shows these).\n"
            "- Do NOT change frontmatter fields like title/description/publishedAt/categories/audience.\n"
            "\n"
            f"Make no more than {self._cfg.max_changes} discrete edits.\n"
            "Return STRICT JSON only.\n"
        )

        user = {
            "post": {"title": title, "audience": audience, "category": category},
            "sections": {"intro_md": intro_md, "how_md": how_md},
            "products": products_min,
            "picks": picks_min,
            "known_common_typos": [
                {"wrong": "lap compartment", "better": "laptop compartment", "note": "If it's clearly about a laptop pocket; otherwise rewrite to avoid the term."},
            ],
            "requirements": {
                "max_pick_sentences": self._cfg.max_pick_sentences,
                "skip_sentence_prefix": "Skip it if",
            },
            "output_schema": {
                "intro_md": "string",
                "how_md": "string",
                "picks": "array of {pick_id: string, body: string}",
                "changes_made": "array of short strings",
            },
        }

        data = self._llm.complete_json(system=system, user=str(user))

        intro_out = data.get("intro_md")
        how_out = data.get("how_md")
        picks_out = data.get("picks")

        if not isinstance(intro_out, str) or not intro_out.strip():
            intro_out = intro_md
        if not isinstance(how_out, str) or not how_out.strip():
            how_out = how_md

        if not isinstance(picks_out, list):
            picks_out = picks_min

        # Keep pick_ids stable + preserve order
        by_id_in = {p["pick_id"]: p for p in picks_min if p.get("pick_id")}
        normalized_picks: list[dict[str, Any]] = []
        seen: set[str] = set()
        for p in picks_out:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("pick_id") or "").strip()
            if not pid or pid not in by_id_in or pid in seen:
                continue
            body = str(p.get("body") or "").strip()
            normalized_picks.append({"pick_id": pid, "body": body})
            seen.add(pid)

        # Ensure we didn't drop any picks
        for p in picks_min:
            pid = p.get("pick_id")
            if pid and pid not in seen:
                normalized_picks.append({"pick_id": pid, "body": str(p.get("body") or "").strip()})

        changes = data.get("changes_made", [])
        if not isinstance(changes, list):
            changes = []
        changes = [c for c in changes if isinstance(c, str)][: self._cfg.max_changes]

        return {
            "intro_md": intro_out.strip(),
            "how_md": how_out.strip(),
            "picks": normalized_picks,
            "changes_made": changes,
        }
