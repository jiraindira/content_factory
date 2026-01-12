"""Title optimization agent (short, human, non-spam).

Deterministic: given the same input, returns the same ordered candidates and selections.

Strategy:
- Generate short, human titles (mostly noun phrases).
- Hard reject clickbait / template-y phrasing.
- Enforce tight length limits.
- Score for keyword coverage, brevity, and uniqueness vs existing titles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from agents.base import BaseAgent
from schemas.title import TitleCandidate, TitleOptimizationInput, TitleOptimizationOutput


# -----------------------------
# Normalization + similarity
# -----------------------------

def normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())

def tokenize(text: str) -> list[str]:
    t = normalize_text(text)
    out: list[str] = []
    cur: list[str] = []
    for ch in t:
        if ch.isalnum():
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    return out

def token_overlap_similarity(a: str, b: str) -> float:
    """Jaccard similarity over token sets."""
    a_tokens = set(tokenize(a))
    b_tokens = set(tokenize(b))
    union = a_tokens | b_tokens
    if not union:
        return 0.0
    return len(a_tokens & b_tokens) / len(union)

def _format_title(title: str) -> str:
    return " ".join((title or "").strip().split())

def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = normalize_text(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


# -----------------------------
# Guardrails (anti-clickbait)
# -----------------------------

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "with", "from", "your",
    "this", "that", "these", "those",
}

# Phrases that make titles feel spammy / blog-template-y.
BANNED_PHRASES_BASE = [
    "top", "best", "ultimate", "must-have", "must have", "game changer",
    "you need", "what to buy", "worth buying", "explained",
    "no-nonsense", "no nonsense", "without overthinking",
    "mistakes", "pitfalls", "checklist", "hacks",
    "buyers guide", "buying guide", "a practical guide",
    "last-minute", "last minute", "this season", "this season’s", "this season's",
    "kickstart", "goals",  # tends to create corporate-y fluff when stacked
]

# Intent/template tokens. If a title contains 2+ of these, it’s almost always “template soup”.
INTENT_TOKENS = [
    "how to", "guide", "explained", "checklist", "mistakes", "pitfalls",
    "what to buy", "worth buying", "picks",
]

def _voice_config(voice: str) -> dict[str, Any]:
    v = normalize_text(voice)
    if v in {"wirecutterish", "wirecutter"}:
        return {
            "banned_phrases": BANNED_PHRASES_BASE + ["premium", "high-impact", "no-brainer"],
            "allowed_soft_words": {"good", "simple", "reliable"},
        }
    if v in {"nerdwalletish", "nerdwallet"}:
        return {
            "banned_phrases": BANNED_PHRASES_BASE + ["insane", "crazy", "secret"],
            "allowed_soft_words": {"simple", "practical"},
        }
    return {
        "banned_phrases": BANNED_PHRASES_BASE,
        "allowed_soft_words": set(),
    }

def _starts_with_any_prefix(title: str, prefixes: Iterable[str]) -> bool:
    t = normalize_text(title)
    for prefix in prefixes:
        p = normalize_text(prefix)
        if p and t.startswith(p):
            return True
    return False

def _count_intent_hits(title: str) -> int:
    t = normalize_text(title)
    return sum(1 for token in INTENT_TOKENS if token in t)

def _looks_spammy(title: str, banned_phrases: list[str]) -> tuple[bool, str]:
    t = normalize_text(title)

    # punctuation bloat / shouting
    if title.count(":") > 1:
        return True, "Too many colons"
    if "!!" in title or "??" in title:
        return True, "Shouty punctuation"
    if "(" in title or ")" in title:
        return True, "Parentheses feel template-y"

    # intent soup
    if _count_intent_hits(title) >= 2:
        return True, "Multiple template intents"

    # banned phrases (hard)
    for phrase in banned_phrases:
        p = normalize_text(phrase)
        if p and p in t:
            return True, f"Contains banned phrase: {phrase}"

    return False, ""


# -----------------------------
# Title generation (short + human)
# -----------------------------

@dataclass(frozen=True)
class _Pattern:
    name: str
    build: Callable[[TitleOptimizationInput], list[str]]

def _topic_phrases(topic: str) -> list[str]:
    """Extract a couple short, deterministic phrases from the topic."""
    toks = [x for x in tokenize(topic) if x not in STOPWORDS]
    if not toks:
        return []
    # two and three token snippets (title-cased)
    out: list[str] = []
    two = " ".join(toks[:2]).title()
    three = " ".join(toks[:3]).title()
    if two:
        out.append(two)
    if three and three != two:
        out.append(three)
    return out

def _secondary_phrases(secondaries: list[str]) -> list[str]:
    """Clean, short secondary phrases; deterministic order."""
    out: list[str] = []
    for sk in secondaries:
        s = _format_title(sk)
        if not s:
            continue
        # keep short secondaries only (avoid dumping long SEO strings into titles)
        if len(s) <= 24:
            out.append(s)
    return out[:8]

def _patterns() -> list[_Pattern]:
    def plain(inp: TitleOptimizationInput) -> list[str]:
        return [inp.primary_keyword.strip()]

    def pk_for_secondary(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [f"{pk} for {s}" for s in _secondary_phrases(inp.secondary_keywords)]

    def pk_for_topic(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [f"{pk} for {p}" for p in _topic_phrases(inp.topic or "")]

    def topic_colon_pk(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [f"{p}: {pk}" for p in _topic_phrases(inp.topic or "")]

    def choosing(inp: TitleOptimizationInput) -> list[str]:
        # Keep these minimal and not “How to…”
        pk = inp.primary_keyword.strip()
        return [f"Choosing {pk}", f"Picking {pk}"]

    return [
        _Pattern("plain", plain),
        _Pattern("pk-secondary", pk_for_secondary),
        _Pattern("pk-topic", pk_for_topic),
        _Pattern("topic-first", topic_colon_pk),
        _Pattern("choosing", choosing),
    ]

def _generate_titles(inp: TitleOptimizationInput, target_count: int) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []

    for pat in _patterns():
        for t in pat.build(inp):
            tt = _format_title(t)
            if tt:
                pairs.append((tt, pat.name))

    # Deterministic de-dupe
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for title, archetype in pairs:
        key = normalize_text(title)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((title, archetype))

    return out[: max(0, target_count)]


# -----------------------------
# Scoring (brevity + relevance + uniqueness)
# -----------------------------

def _length_penalty(n: int) -> float:
    # Sweet spot: 28–52. Hard cap 60. Reject > 70.
    if n < 18:
        return 18.0  # too short/vague
    if n <= 52:
        return 0.0
    if n <= 60:
        return (n - 52) * 1.8
    if n <= 70:
        return 15.0 + (n - 60) * 3.0
    return 100.0

def _keyword_coverage(pk: str, title: str) -> tuple[float, str]:
    pk_tokens = [t for t in tokenize(pk) if t not in STOPWORDS]
    title_tokens = set(tokenize(title))
    if not pk_tokens:
        return 0.0, "No primary keyword tokens"
    covered = sum(1 for t in pk_tokens if t in title_tokens)
    ratio = covered / len(pk_tokens)
    if ratio >= 1.0:
        return 45.0, "Primary keyword match"
    if ratio >= 0.8:
        return 36.0, "Strong keyword match"
    if ratio >= 0.6:
        return 24.0, "Partial keyword match"
    if ratio >= 0.4:
        return 12.0, "Weak keyword match"
    return 0.0, "Keyword mismatch"

def _secondary_bonus(secondaries: list[str], title: str) -> float:
    title_tokens = set(tokenize(title))
    bonus = 0.0
    for sk in secondaries:
        sk_tokens = [t for t in tokenize(sk) if t not in STOPWORDS]
        if not sk_tokens:
            continue
        if all(t in title_tokens for t in sk_tokens):
            bonus += 2.0
    return min(8.0, bonus)

def _uniqueness(existing_titles: list[str], title: str) -> tuple[float, float]:
    if not existing_titles:
        return 25.0, 0.0
    sims = [token_overlap_similarity(title, t) for t in existing_titles]
    max_sim = max(sims) if sims else 0.0
    return 25.0 * (1.0 - max_sim), max_sim

def _soft_voice_bonus(title: str, allowed_soft_words: set[str]) -> float:
    if not allowed_soft_words:
        return 0.0
    toks = set(tokenize(title))
    hit = len(toks & allowed_soft_words)
    return min(4.0, float(hit) * 2.0)

def _score_title(inp: TitleOptimizationInput, title: str) -> tuple[float, list[str]]:
    reasons: list[str] = []
    title = _format_title(title)

    cfg = _voice_config(inp.voice)
    banned_phrases: list[str] = list(cfg["banned_phrases"])
    allowed_soft_words: set[str] = set(cfg["allowed_soft_words"])

    # Hard rejects
    spammy, why = _looks_spammy(title, banned_phrases)
    if spammy:
        return 0.0, [f"Rejected: {why}"]

    # Length gating
    lp = _length_penalty(len(title))
    if lp >= 90.0:
        return 0.0, ["Rejected: too long"]

    # Keyword gating (must be at least weak match)
    kw, kw_reason = _keyword_coverage(inp.primary_keyword, title)
    if kw <= 0.0:
        return 0.0, [f"Rejected: {kw_reason}"]
    reasons.append(kw_reason)

    sb = _secondary_bonus(inp.secondary_keywords, title)
    if sb > 0:
        reasons.append("Includes secondary detail")

    uq, max_sim = _uniqueness(inp.existing_titles, title)
    if max_sim >= 0.6:
        reasons.append("Very similar to existing title")
    elif max_sim >= 0.35:
        reasons.append("Somewhat similar to existing title")
    else:
        reasons.append("Distinct from existing titles")

    vb = _soft_voice_bonus(title, allowed_soft_words)
    if vb > 0:
        reasons.append("Voice fit")

    # Final score
    score = 100.0
    score -= lp
    score -= (45.0 - kw)  # enforce primary keyword coverage
    score += sb
    score += uq
    score += vb

    score = max(0.0, min(100.0, score))
    return float(round(score, 2)), _dedupe_preserve_order(reasons)


# -----------------------------
# Agent
# -----------------------------

class TitleOptimizationAgent(BaseAgent):
    """Generate, filter, and score short, human blog titles."""

    name = "title-optimization"

    def run(self, input: TitleOptimizationInput | dict) -> dict[str, Any]:
        inp = input if isinstance(input, TitleOptimizationInput) else TitleOptimizationInput(**input)

        # Generate a small pool (deterministic)
        raw_pairs = _generate_titles(inp, target_count=inp.num_candidates * 2)

        # Apply user-configured banned starts (monoculture prevention)
        filtered_pairs = [
            (t, a) for (t, a) in raw_pairs if not _starts_with_any_prefix(t, inp.banned_starts)
        ]

        scored: list[TitleCandidate] = []
        for title, archetype in filtered_pairs:
            score, reasons = _score_title(inp, title)
            if score <= 0:
                continue
            scored.append(
                TitleCandidate(
                    title=title,
                    archetype=archetype,
                    score=score,
                    reasons=reasons,
                )
            )

        scored_sorted = sorted(
            scored,
            key=lambda c: (-c.score, normalize_text(c.title), normalize_text(c.archetype)),
        )

        candidates = scored_sorted[: inp.num_candidates]

        # Select top-N with light archetype diversity
        selected: list[TitleCandidate] = []
        seen_arch: set[str] = set()
        for c in candidates:
            if c.archetype not in seen_arch or len(selected) < 2:
                selected.append(c)
                seen_arch.add(c.archetype)
            if len(selected) == inp.return_top_n:
                break

        output = TitleOptimizationOutput(selected=selected, candidates=candidates)
        return output.model_dump() if hasattr(output, "model_dump") else output.dict()
