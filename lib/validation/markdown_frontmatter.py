from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Tuple

import yaml


_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class FrontmatterParseResult:
    data: Dict[str, Any]
    body: str
    frontmatter_text: str


def parse_markdown_frontmatter(md_text: str) -> FrontmatterParseResult:
    """
    Parses YAML frontmatter from a markdown file.

    Returns:
      - data: dict of frontmatter
      - body: markdown content after frontmatter
      - frontmatter_text: original YAML block (without delimiters)
    """
    m = _FRONTMATTER_RE.match(md_text)
    if not m:
        # No frontmatter
        return FrontmatterParseResult(data={}, body=md_text, frontmatter_text="")

    fm_text = m.group(1)
    body = md_text[m.end():]

    try:
        data = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Frontmatter must be a YAML mapping/object.")

    return FrontmatterParseResult(data=data, body=body, frontmatter_text=fm_text)


def rebuild_markdown_with_frontmatter(frontmatter: Dict[str, Any], body: str) -> str:
    """
    Rebuild markdown with YAML frontmatter. Uses safe_dump with stable formatting.
    """
    fm_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{fm_text}\n---\n\n{body.lstrip()}"
