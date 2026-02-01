from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def load_factory_schema() -> dict[str, Any]:
    """Load the canonical factory schema YAML used as data-driven validation input."""
    schema_path = _repo_root() / "ai_content_factory_schema.yaml"
    with schema_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Factory schema file did not parse to a dict")
    return data


def load_illegal_matrix() -> dict[str, Any]:
    schema = load_factory_schema()
    matrix = schema.get("illegal_matrix")
    if not isinstance(matrix, dict):
        raise ValueError("Factory schema is missing illegal_matrix")
    return matrix
