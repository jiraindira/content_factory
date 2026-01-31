from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ProductTypeSummary:
    counts: dict[str, int]
    total: int
    major_types: tuple[str, ...]
    is_mixed: bool


_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {m.group(0) for m in _WORD_RE.finditer((text or "").lower())}


def classify_product_type(text: str) -> str | None:
    """Very small heuristic classifier based on product title/description."""
    t = (text or "").lower()
    toks = _tokens(t)

    if "umbrella" in toks:
        return "umbrella"

    if "poncho" in toks:
        return "poncho"

    if "raincoat" in toks or ("rain" in toks and "coat" in toks):
        return "raincoat"

    # Common variants
    if "rain" in toks and "jacket" in toks:
        return "raincoat"

    if "waterproof" in toks and ("jacket" in toks or "coat" in toks):
        return "raincoat"

    # UK-ish wording
    if "mac" in toks or "mack" in toks:
        # Very loose; only treat as raincoat if also rain/waterproof is present
        if "rain" in toks or "waterproof" in toks:
            return "raincoat"

    return None


def summarize_product_types(products: Iterable[dict]) -> ProductTypeSummary:
    counts: dict[str, int] = {}
    total = 0

    for p in products or []:
        if not isinstance(p, dict):
            continue
        text = " ".join(
            [
                str(p.get("title", "") or ""),
                str(p.get("name", "") or ""),
                str(p.get("description", "") or ""),
            ]
        ).strip()
        if not text:
            continue
        total += 1
        t = classify_product_type(text)
        if not t:
            continue
        counts[t] = counts.get(t, 0) + 1

    # Determine major types: at least 2 occurrences OR at least 25% of identified items
    major: list[str] = []
    denom = max(1, total)
    for t, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if c >= 2 or (c / denom) >= 0.25:
            major.append(t)

    is_mixed = len(major) >= 2
    return ProductTypeSummary(counts=counts, total=total, major_types=tuple(major), is_mixed=is_mixed)


_UMBRELLA_TERMS = {
    "rain gear",
    "raingear",
    "rainwear",
    "rain wear",
    "rain protection",
    "wet weather",
    "wet-weather",
    "rain essentials",
    "travel rain gear",
    "travel rainwear",
}


def title_uses_umbrella_term(title: str) -> bool:
    t = (title or "").lower()
    return any(term in t for term in _UMBRELLA_TERMS)


def title_mentions_type(title: str, t: str) -> bool:
    title_l = (title or "").lower()
    if t == "raincoat":
        return any(x in title_l for x in ["raincoat", "rain coat", "rain jacket", "waterproof jacket", "waterproof coat"])
    if t == "poncho":
        return "poncho" in title_l
    if t == "umbrella":
        return "umbrella" in title_l
    return t in title_l
