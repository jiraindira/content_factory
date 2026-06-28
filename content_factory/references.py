"""
Client reference material (books / manuscripts) for grounded generation.

A client's book is extracted to plain text and stored at
content_factory/references/<brand_id>.txt. At generation time the text is
passed to Claude as prompt-cached source material so articles are grounded
in the client's actual frameworks and language.
"""
from __future__ import annotations

import io
from pathlib import Path

REFERENCES_DIR = Path(__file__).parent / "references"

# Cap stored text so a very large book stays within context and predictable cost.
# ~600K chars ≈ ~150K tokens — comfortably inside Claude's 1M window.
MAX_CHARS = 600_000


def reference_path(brand_id: str) -> Path:
    return REFERENCES_DIR / f"{brand_id}.txt"


def extract_pdf_text(data: bytes) -> str:
    """Extract plain text from a PDF byte stream."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n\n".join(p.strip() for p in parts if p.strip())
    # Normalise excessive whitespace from PDF extraction
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def save_reference_text(brand_id: str, text: str) -> Path:
    REFERENCES_DIR.mkdir(parents=True, exist_ok=True)
    text = (text or "").strip()
    truncated = text[:MAX_CHARS]
    path = reference_path(brand_id)
    path.write_text(truncated, encoding="utf-8")
    return path


def load_reference_text(brand_id: str | None) -> str | None:
    if not brand_id:
        return None
    path = reference_path(brand_id)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def delete_reference(brand_id: str) -> bool:
    path = reference_path(brand_id)
    if path.exists():
        path.unlink()
        return True
    return False


def reference_meta(brand_id: str) -> dict:
    """Lightweight status used by the admin UI."""
    text = load_reference_text(brand_id)
    if not text:
        return {"exists": False}
    word_count = len(text.split())
    return {
        "exists": True,
        "word_count": word_count,
        "char_count": len(text),
        "truncated": len(text) >= MAX_CHARS,
        "approx_tokens": round(len(text) / 4),
    }
