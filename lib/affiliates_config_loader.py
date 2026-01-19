from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from schemas.affiliates_config import AffiliatesConfig


DEFAULT_AFFILIATES_CONFIG_PATH = Path("config/affiliates.yaml")


def load_affiliates_config(path: Optional[Path] = None) -> AffiliatesConfig:
    """
    Loads and validates affiliates config.
    """
    p = path or DEFAULT_AFFILIATES_CONFIG_PATH
    if not p.exists():
        raise FileNotFoundError(f"Affiliates config file not found: {p}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cfg = AffiliatesConfig.model_validate(raw)

    # Basic sanity checks
    if cfg.default_provider not in cfg.providers:
        raise ValueError(
            f"default_provider '{cfg.default_provider}' not found in providers. "
            f"Known providers: {sorted(cfg.providers.keys())}"
        )

    return cfg
