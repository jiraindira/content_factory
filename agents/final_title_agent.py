from __future__ import annotations

import re
from dataclasses import dataclass

from integrations.openai_adapters import OpenAIJsonLLM
from agents.title_validation import validate_title_semantics
from lib.product_type_summary import summarize_product_types


@dataclass(frozen=True)
class FinalTitleConfig:
    max_chars: int = 60
    num_candidates: int = 12
    banned_starts: tuple[str, ...] = (
        "Top",
        "Best",
        "Ultimate",
        "Must-Have",
        "You Need",
        "Our Favorite",
        "Top Picks",
        "Best Picks",
    )


_TITLECASE_SMALL_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "if", "in",
    "into", "nor", "of", "on", "or", "over", "per", "the", "to", "vs", "via", "with",
}


_ACRONYM_RE = re.compile(r"^[A-Z0-9]{2,}$")


def _titlecase_word(w: str) -> str:
    if not w:
        return w
    if _ACRONYM_RE.match(w):
        return w
    if "'" in w:
        parts = w.split("'")
        head = parts[0]
        tail = "'".join(parts[1:])
        return head[:1].upper() + head[1:].lower() + ("'" + tail.lower() if tail else "")
    return w[:1].upper() + w[1:].lower()


def to_title_case(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return s
    s = re.sub(r"\s{2,}", " ", s)

    words = s.split(" ")
    out: list[str] = []

    for i, raw in enumerate(words):
        hy_parts = raw.split("-")
        transformed_parts: list[str] = []

        for j, part in enumerate(hy_parts):
            stripped = re.sub(r"^[^A-Za-z0-9]*|[^A-Za-z0-9]*$", "", part)
            prefix = part[: part.find(stripped)] if stripped and stripped in part else ""
            suffix = part[part.find(stripped) + len(stripped):] if stripped and stripped in part else ""

            core = stripped
            core_lower = core.lower()

            is_first = (i == 0 and j == 0)
            is_last = (i == len(words) - 1 and j == len(hy_parts) - 1)

            if not core:
                transformed_parts.append(part)
                continue

            if (not is_first and not is_last) and core_lower in _TITLECASE_SMALL_WORDS:
                core_tc = core_lower
            else:
                core_tc = _titlecase_word(core)

            transformed_parts.append(prefix + core_tc + suffix)

        out.append("-".join(transformed_parts))

    return " ".join(out)


def _clean_title(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s{2,}", " ", s)
    s = s.rstrip(" .!?,;:")
    return s


def _banned_start(s: str, banned: tuple[str, ...]) -> bool:
    s_stripped = (s or "").strip()
    for b in banned:
        if s_stripped.lower().startswith(b.lower()):
            return True
    return False


def _truncate_to_max_chars(title: str, max_chars: int) -> str:
    title = _clean_title(title)
    if len(title) <= max_chars:
        return title

    cut = title[:max_chars].rstrip()
    for sep in [":", "–", "-", ","]:
        idx = cut.rfind(sep)
        if idx >= 30:
            return cut[:idx].rstrip()

    idx = cut.rfind(" ")
    if idx >= 30:
        return cut[:idx].rstrip()

    return cut.rstrip()


class FinalTitleAgent:
    """
    Generates a calm editorial title after the body exists.
    Pipeline:
      1) LLM generates candidates.
      2) Deterministic validator rejects semantically mismatched titles.
      3) Apply Title Case + max chars.
      4) Pick best remaining (shortest, then lexical).
    """

    def __init__(self, *, llm: OpenAIJsonLLM, config: FinalTitleConfig | None = None) -> None:
        self._llm = llm
        self._cfg = config or FinalTitleConfig()

    def run(
        self,
        *,
        topic: str,
        category: str | None,
        intro: str,
        picks: list[str],
        products: list[dict],
        alternatives: str | None = None,
        user_hint_title: str | None = None,
        user_hint_description: str | None = None,
    ) -> str:
        # Hard override (user-provided) is handled by the caller.

        picks_snip = "\n".join(f"- {p[:220]}" for p in (picks or [])[:5])

        product_titles = [
            str(p.get("title") or p.get("name") or "").strip()
            for p in (products or [])
            if isinstance(p, dict) and str(p.get("title") or p.get("name") or "").strip()
        ]
        products_snip = "\n".join(f"- {t[:140]}" for t in product_titles[:10])

        mix = summarize_product_types(products or [])
        mix_str = ", ".join(f"{k}={v}" for k, v in sorted(mix.counts.items())) or "(unknown)"

        system = (
            "You are a calm editorial headline writer.\n"
            "Write short, human-first titles for skimmable buying guides.\n"
            "Hard rules:\n"
            f"- Max {self._cfg.max_chars} characters.\n"
            "- No clickbait.\n"
            "- No promises of testing.\n"
            "- Avoid 'Top', 'Best', 'Ultimate', 'Must-Have' style openers.\n"
            "- Avoid overfitting to a specific city (e.g., London) unless explicitly requested.\n"
            "Return JSON with key: candidates (array of strings).\n"
        )

        user = (
            f"TOPIC: {topic}\n"
            f"CATEGORY: {category or 'n/a'}\n\n"
            f"PRODUCT MIX (heuristic): {mix_str}\n"
            f"MIXED SET: {'yes' if mix.is_mixed else 'no'}\n\n"
            f"PRODUCT TITLES (sample):\n{products_snip}\n\n"
            f"USER TITLE HINT (optional): {user_hint_title or ''}\n"
            f"USER DESCRIPTION HINT (optional): {(user_hint_description or '')[:300]}\n\n"
            f"INTRO (excerpt):\n{(intro or '')[:500]}\n\n"
            f"PICKS (excerpts):\n{picks_snip}\n\n"
            f"Generate {self._cfg.num_candidates} candidate titles.\n"
            "Keep them plainspoken and specific.\n"
            "No colons unless truly needed.\n"
            "If the product set is mixed (e.g., umbrellas + ponchos + raincoats), prefer an umbrella title like '\n"
            "Travel rain gear essentials' rather than naming only one subtype.\n"
        )

        data = self._llm.complete_json(system=system, user=user)
        raw_candidates = data.get("candidates", [])
        if not isinstance(raw_candidates, list):
            raw_candidates = []

        # Normalize candidates
        cleaned: list[str] = []
        for c in raw_candidates:
            if not isinstance(c, str):
                continue
            c = _clean_title(c)
            if not c:
                continue
            if _banned_start(c, self._cfg.banned_starts):
                continue
            cleaned.append(c)

        # Validate semantics before formatting
        valid: list[str] = []
        for c in cleaned:
            v = validate_title_semantics(
                title=c,
                products=products or [],
                intro=intro or "",
                picks=picks or [],
                alternatives=alternatives,
            )
            if v.ok:
                valid.append(c)

        # If none pass, fall back to a safe, truthful template
        if not valid:
            # Pick a conservative noun based on inferred mode from validator
            # We infer mode from a representative check on topic itself
            v = validate_title_semantics(
                title=topic,
                products=products or [],
                intro=intro or "",
                picks=picks or [],
                alternatives=alternatives,
            )
            topic_clean = re.sub(r"[_\-]+", " ", str(topic or "")).strip()

            # Prefer umbrella wording for mixed physical sets.
            if mix.is_mixed and (category or "").strip().lower() == "travel":
                base = "Travel rain gear essentials"
            elif mix.is_mixed:
                base = f"{topic_clean} essentials" if topic_clean else "Travel rain gear essentials"
            elif v.inferred_mode in {"digital_only", "mixed"}:
                base = f"Tools for Managing {topic_clean or topic}"
            else:
                # Physical-only: keep it simple and non-clicky.
                base = f"{topic_clean or topic} essentials"

            base = _truncate_to_max_chars(base, self._cfg.max_chars)
            return to_title_case(base)

        # Apply formatting and max length after validation
        formatted: list[str] = []
        for c in valid:
            c2 = to_title_case(c)
            c2 = _truncate_to_max_chars(c2, self._cfg.max_chars)
            if c2 and not _banned_start(c2, self._cfg.banned_starts):
                formatted.append(c2)

        if not formatted:
            fallback = to_title_case(_truncate_to_max_chars(topic, self._cfg.max_chars))
            if _banned_start(fallback, self._cfg.banned_starts):
                fallback = to_title_case(_truncate_to_max_chars(f"{topic} Guide", self._cfg.max_chars))
            return fallback

        formatted = sorted(set(formatted), key=lambda x: (len(x), x))
        return formatted[0]
