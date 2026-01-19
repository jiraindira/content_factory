from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from lib.affiliates_config_loader import load_affiliates_config
from schemas.affiliates_config import AffiliatesConfig


@dataclass(frozen=True)
class AffiliateRoutingResult:
    provider_id: str
    reason: str


def _compile_signal_regex(signals: list[str]) -> re.Pattern[str]:
    # Sort longest first to match multi-word phrases before substrings
    parts = [re.escape(s.strip()) for s in sorted({s for s in signals if (s or "").strip()}, key=len, reverse=True)]
    if not parts:
        # never-matching regex
        return re.compile(r"a^")
    return re.compile(r"|".join(parts), re.IGNORECASE)


class AffiliateRoutingAgent:
    """
    Deterministic routing engine driven by config.

    Policy lives in config/affiliates.yaml
    Mechanism lives here.
    """

    def __init__(self, *, config_path: Optional[Path] = None) -> None:
        self._cfg: AffiliatesConfig = load_affiliates_config(config_path)

        # Precompile signal-group regexes for performance + determinism
        self._signal_group_res: dict[str, re.Pattern[str]] = {}
        for group_id, signals in self._cfg.signal_groups.items():
            self._signal_group_res[group_id] = _compile_signal_regex(signals)

    def run(self, *, category: str, topic: str) -> AffiliateRoutingResult:
        cat = (category or "").strip().lower()
        t = (topic or "").strip()

        # 1) Candidate providers must support the category
        candidates: list[str] = []
        for pid, p in self._cfg.providers.items():
            cats = {c.strip().lower() for c in (p.categories or [])}
            if cat in cats:
                candidates.append(pid)

        # If nothing matches, fall back to default
        if not candidates:
            return AffiliateRoutingResult(
                provider_id=self._cfg.default_provider,
                reason=f"No providers matched category '{category}'. Falling back to default.",
            )

        # 2) Enforce signal requirements (e.g., Mountain Warehouse outdoor gear only)
        eligible: list[str] = []
        reasons: list[str] = []

        for pid in candidates:
            p = self._cfg.providers[pid]
            group = p.requires_signal_group
            if not group:
                eligible.append(pid)
                reasons.append(f"{pid}: eligible (no signal group required)")
                continue

            rx = self._signal_group_res.get(group)
            if rx is None:
                # Misconfigured group -> treat as not eligible and explain
                reasons.append(f"{pid}: NOT eligible (missing signal group '{group}' in config)")
                continue

            if rx.search(t):
                eligible.append(pid)
                reasons.append(f"{pid}: eligible (matched signal group '{group}')")
            else:
                reasons.append(f"{pid}: NOT eligible (did not match signal group '{group}')")

        if not eligible:
            return AffiliateRoutingResult(
                provider_id=self._cfg.default_provider,
                reason=(
                    f"Providers matched category '{category}' but none met signal requirements. "
                    f"Falling back to default. Details: {', '.join(reasons)}"
                ),
            )

        # 3) If default provider is eligible, prefer it unless a more specific provider is eligible.
        # Specific providers are those with requires_signal_group set.
        specific = [pid for pid in eligible if self._cfg.providers[pid].requires_signal_group]
        if specific:
            chosen = specific[0]
            return AffiliateRoutingResult(
                provider_id=chosen,
                reason=f"Chose specific provider '{chosen}'. Details: {', '.join(reasons)}",
            )

        # Otherwise, choose default if possible; else first eligible
        if self._cfg.default_provider in eligible:
            return AffiliateRoutingResult(
                provider_id=self._cfg.default_provider,
                reason=f"Default provider eligible for category '{category}'. Details: {', '.join(reasons)}",
            )

        chosen = eligible[0]
        return AffiliateRoutingResult(
            provider_id=chosen,
            reason=f"Chose first eligible provider '{chosen}'. Details: {', '.join(reasons)}",
        )
