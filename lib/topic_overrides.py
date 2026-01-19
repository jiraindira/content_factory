from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from schemas.topic_override import TopicOverridesFile, TopicOverride


DEFAULT_OVERRIDES_PATH = Path("config/topic_overrides.yaml")


def load_topic_override_for_date(
    *,
    date_str: str,
    overrides_path: Path | None = None,
) -> Optional[TopicOverride]:
    path = overrides_path or DEFAULT_OVERRIDES_PATH
    if not path.exists():
        return None

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parsed = TopicOverridesFile.model_validate(raw)

    for o in parsed.overrides:
        if o.date == date_str:
            return o
    return None
