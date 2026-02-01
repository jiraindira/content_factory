from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field

from schemas.base import SchemaBase


class BlockType(str, Enum):
    paragraph = "paragraph"
    bullets = "bullets"
    numbered = "numbered"
    callout = "callout"
    quote = "quote"
    divider = "divider"


class Block(SchemaBase):
    type: BlockType
    text: Optional[str] = None
    items: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None


class Section(SchemaBase):
    id: str
    heading: Optional[str] = None
    blocks: List[Block] = Field(default_factory=list)


class Product(SchemaBase):
    pick_id: str
    title: str
    url: str
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    provider: Optional[str] = None


class Rationale(SchemaBase):
    how_chosen_blocks: List[Block] = Field(default_factory=list)
    selection_criteria: List[str] = Field(default_factory=list)


class ClaimType(str, Enum):
    fact = "fact"
    inference = "inference"
    opinion = "opinion"
    advice = "advice"


class Claim(SchemaBase):
    id: str
    text: str
    claim_type: ClaimType
    requires_citation: bool
    supported_by_source_ids: List[str] = Field(default_factory=list)


class SourceKind(str, Enum):
    url = "url"
    file = "file"


class Source(SchemaBase):
    source_id: str
    kind: SourceKind
    ref: str
    purpose: str
    notes: Optional[str] = None


class Checks(SchemaBase):
    matrix_validation_passed: bool
    brand_policy_checks_passed: bool
    required_sections_present: bool
    products_present_when_required: bool
    citations_present_when_required: bool
    topic_allowlist_passed: bool
    required_disclaimers_present: bool
    robots_policy_passed: bool
    disallowed_claims_found: List[str] = Field(default_factory=list)


class ContentArtifact(SchemaBase):
    artifact_version: str = "1.0"
    brand_id: str
    run_id: str
    generated_at: str

    intent: str
    form: str
    domain: str
    content_depth: str

    audience: Dict[str, Any]
    persona: Dict[str, Any]

    sections: List[Section]

    products: Optional[List[Product]] = None
    rationale: Rationale

    claims: List[Claim] = Field(default_factory=list)
    sources: List[Source] = Field(default_factory=list)

    checks: Checks
