from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class UrlFixResult:
    original: str
    normalized: str
    changed: bool


def normalize_url(raw: str) -> UrlFixResult:
    """
    Normalize common URL inputs into a fully-qualified http(s) URL.
    Safe normalizations only. Anything ambiguous remains invalid.

    Rules:
      - If already valid http(s) URL -> unchanged
      - If starts with 'www.' -> prefix https://
      - If starts with 'amzn.to/' -> prefix https://
      - If starts with 'amazon.' -> prefix https://
      - If starts with 'www.amzn.to/' -> prefix https://
    """
    if raw is None:
        raise ValueError("URL is None")

    s = str(raw).strip()
    if not s:
        raise ValueError("URL is empty")

    lowered = s.lower()

    # Safe prefixing for common cases where scheme is omitted
    if lowered.startswith("www."):
        s2 = "https://" + s
        return UrlFixResult(original=s, normalized=s2, changed=True)

    if lowered.startswith("amzn.to/"):
        s2 = "https://" + s
        return UrlFixResult(original=s, normalized=s2, changed=True)

    if lowered.startswith("www.amzn.to/"):
        s2 = "https://" + s
        return UrlFixResult(original=s, normalized=s2, changed=True)

    if lowered.startswith("amazon."):
        s2 = "https://" + s
        return UrlFixResult(original=s, normalized=s2, changed=True)

    # Validate fully qualified URL
    parsed = urlparse(s)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return UrlFixResult(original=s, normalized=s, changed=False)

    # Reject relative URLs or malformed inputs
    raise ValueError(f"Invalid url: {s}")


def is_valid_http_url(raw: str) -> bool:
    try:
        res = normalize_url(raw)
        parsed = urlparse(res.normalized)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False
