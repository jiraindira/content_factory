"""Title optimization agent.

This agent is intentionally deterministic: given the same input it will always
produce the same ordered candidate list and selections.

It generates a pool of candidate titles from a fixed set of archetypes,
filters out overused prefixes, scores candidates 0–100, and returns the top-N.

Scoring (0–100):
- Keyword presence: primary keyword weighted highest; secondary keywords add lift.
- Clarity: penalizes overly long titles (> 80 characters).
- Uniqueness: penalizes similarity vs existing titles using simple token overlap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from agents.base import BaseAgent
from schemas.title import (
    TitleCandidate,
    TitleOptimizationInput,
    TitleOptimizationOutput,
)


def normalize_text(text: str) -> str:
    """Normalize text for comparisons.

    Lowercases and collapses whitespace.
    """
    return " ".join((text or "").strip().lower().split())


def tokenize(text: str) -> list[str]:
    """Tokenize text into simple alphanumeric tokens.

    This is a lightweight tokenizer intended for similarity checks.
    """
    normalized = normalize_text(text)
    tokens: list[str] = []
    current: list[str] = []

    for ch in normalized:
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                tokens.append("".join(current))
                current = []

    if current:
        tokens.append("".join(current))

    return tokens


def token_overlap_similarity(a: str, b: str) -> float:
    """Compute simple token-overlap similarity between two strings.

    Uses Jaccard similarity on token sets: |A ∩ B| / |A ∪ B|.
    Returns 0.0 for empty unions.
    """
    a_tokens = set(tokenize(a))
    b_tokens = set(tokenize(b))
    union = a_tokens | b_tokens
    if not union:
        return 0.0
    return len(a_tokens & b_tokens) / len(union)


def _starts_with_any_prefix(title: str, prefixes: Iterable[str]) -> bool:
    """Case-insensitive startswith check against a list of prefixes."""
    t = normalize_text(title)
    for prefix in prefixes:
        p = normalize_text(prefix)
        if p and t.startswith(p):
            return True
    return False


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    """Deduplicate strings preserving order (case-insensitive via normalize_text)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = normalize_text(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _format_title(title: str) -> str:
    """Light formatting for titles (trim, collapse whitespace)."""
    return " ".join((title or "").strip().split())


@dataclass(frozen=True)
class _Archetype:
    name: str
    build: Callable[[TitleOptimizationInput], list[str]]


def _archetypes() -> list[_Archetype]:
    """Return the ordered list of title archetypes.

    Keep this deterministic and stable: ordering affects candidate order.
    """

    def primary_first(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [
            f"{pk}: A Practical Guide for {inp.topic}",
            f"{pk} Explained: What to Buy and Why",
            f"{pk} for Real Life: What Actually Works",
        ]

    def how_to(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [
            f"How to Choose the Right {pk} (Without Overthinking)",
            f"How to Shop for {pk}: A No-Nonsense Checklist",
            f"How to Get the Most from {pk} This Season",
        ]

    def mistakes(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [
            f"Common {pk} Mistakes (and What to Do Instead)",
            f"Avoid These {pk} Pitfalls: A Quick Guide",
            f"Before You Buy: {pk} Mistakes to Avoid",
        ]

    def budget(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [
            f"Great {pk} on a Budget: What to Look For",
            f"The Best Value {pk}: Smart Picks That Hold Up",
            f"Affordable {pk} That Still Feel Premium",
        ]

    def comparisons(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [
            f"{pk} Buying Guide: What Matters (and What Doesn’t)",
            f"{pk} Breakdown: Features Worth Paying For",
            f"{pk} 101: The Key Features to Prioritize",
        ]

    def giftable(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [
            f"Giftable {pk}: Thoughtful Picks People Use",
            f"The Most Giftable {pk} for {inp.topic}",
            f"Last-Minute {pk} Gifts That Don’t Feel Last-Minute",
        ]

    def seasonal(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [
            f"{pk} for Right Now: Seasonal Picks for {inp.topic}",
            f"This Season’s {pk}: What’s Worth Buying",
            f"A Seasonal Guide to {pk} You’ll Actually Use",
        ]

    def audience_focus(inp: TitleOptimizationInput) -> list[str]:
        pk = inp.primary_keyword.strip()
        return [
            f"{pk} for Beginners: Simple, Reliable Choices",
            f"{pk} for Busy People: Low-Effort, High-Impact Picks",
            f"{pk} for Small Spaces: Compact Options That Work",
        ]

    return [
        _Archetype("primary-first", primary_first),
        _Archetype("how-to", how_to),
        _Archetype("mistakes", mistakes),
        _Archetype("budget", budget),
        _Archetype("comparisons", comparisons),
        _Archetype("giftable", giftable),
        _Archetype("seasonal", seasonal),
        _Archetype("audience-focus", audience_focus),
    ]


def _generate_titles(inp: TitleOptimizationInput, *, target_count: int) -> list[tuple[str, str]]:
    """Generate (title, archetype) pairs deterministically."""
    pairs: list[tuple[str, str]] = []

    archetype_lists: list[tuple[str, list[str]]] = [
        (a.name, [_format_title(t) for t in a.build(inp)])
        for a in _archetypes()
    ]

    max_len = max((len(titles) for _, titles in archetype_lists), default=0)
    for i in range(max_len):
        for archetype_name, titles in archetype_lists:
            if i < len(titles):
                pairs.append((titles[i], archetype_name))

    secondaries = [s.strip() for s in inp.secondary_keywords if s and s.strip()]
    pk = inp.primary_keyword.strip()
    for sk in secondaries:
        pairs.append((_format_title(f"{pk} + {sk}: A Smart Buyer’s Guide"), "secondary-combo"))
        pairs.append((_format_title(f"{sk} and {pk}: What to Prioritize"), "secondary-combo"))

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for title, archetype_name in pairs:
        key = normalize_text(title)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append((title, archetype_name))

    return deduped[: max(target_count, 0)]


def _score_title(inp: TitleOptimizationInput, title: str) -> tuple[float, list[str]]:
    """Score a title 0–100 and return (score, reasons)."""
    reasons: list[str] = []

    title_norm = normalize_text(title)
    pk_norm = normalize_text(inp.primary_keyword)

    keyword_score = 0.0
    if pk_norm and pk_norm in title_norm:
        keyword_score += 35.0
        reasons.append("Primary keyword present")
    else:
        pk_tokens = set(tokenize(inp.primary_keyword))
        title_tokens = set(tokenize(title))
        if pk_tokens:
            overlap = len(pk_tokens & title_tokens) / len(pk_tokens)
            if overlap >= 0.8:
                keyword_score += 28.0
                reasons.append("Primary keyword mostly present")
            elif overlap >= 0.5:
                keyword_score += 18.0
                reasons.append("Primary keyword partially present")

    secondary_lift = 0.0
    for sk in inp.secondary_keywords:
        sk_norm = normalize_text(sk)
        if sk_norm and sk_norm in title_norm:
            secondary_lift += 2.5
    secondary_lift = min(10.0, secondary_lift)
    if secondary_lift > 0:
        reasons.append("Includes secondary keywords")

    keyword_component = min(45.0, keyword_score + secondary_lift)

    clarity_component = 20.0
    if len(title) > 80:
        over = len(title) - 80
        penalty = min(20.0, (over / 40.0) * 20.0)
        clarity_component = max(0.0, 20.0 - penalty)
        reasons.append("Too long; clarity penalty")

    if inp.existing_titles:
        similarities = [token_overlap_similarity(title, t) for t in inp.existing_titles]
        max_sim = max(similarities) if similarities else 0.0
    else:
        max_sim = 0.0

    uniqueness_component = 35.0 * (1.0 - max_sim)
    if max_sim >= 0.6:
        reasons.append("Very similar to an existing title")
    elif max_sim >= 0.35:
        reasons.append("Somewhat similar to an existing title")
    else:
        reasons.append("Distinct from existing titles")

    total = keyword_component + clarity_component + uniqueness_component
    total = max(0.0, min(100.0, total))

    return total, reasons


class TitleOptimizationAgent(BaseAgent):
    """Generate, filter, and score SEO-friendly blog titles."""

    name = "title-optimization"

    def run(
        self, input: TitleOptimizationInput | dict
    ) -> dict[str, Any]:
        inp = input if isinstance(input, TitleOptimizationInput) else TitleOptimizationInput(**input)

        raw_pairs = _generate_titles(inp, target_count=inp.num_candidates * 3)

        filtered_pairs = [
            (t, a) for (t, a) in raw_pairs if not _starts_with_any_prefix(t, inp.banned_starts)
        ][: inp.num_candidates]

        scored: list[TitleCandidate] = []
        for title, archetype_name in filtered_pairs:
            score, reasons = _score_title(inp, title)
            scored.append(
                TitleCandidate(
                    title=title,
                    archetype=archetype_name,
                    score=float(round(score, 2)),
                    reasons=_dedupe_preserve_order(reasons),
                )
            )

        scored_sorted = sorted(
            scored,
            key=lambda c: (-c.score, normalize_text(c.title), normalize_text(c.archetype)),
        )

        selected: list[TitleCandidate] = []
        seen_archetypes: set[str] = set()
        for c in scored_sorted:
            if c.archetype not in seen_archetypes or len(selected) < 2:
                selected.append(c)
                seen_archetypes.add(c.archetype)
            if len(selected) == inp.return_top_n:
                break

        output = TitleOptimizationOutput(
            selected=selected,
            candidates=scored_sorted,
        )
        return output.to_dict()
