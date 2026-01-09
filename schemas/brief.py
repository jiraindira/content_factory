from pydantic import Field
from .base import SchemaBase
from .common import KeywordSet, SearchIntent, SiteVoice

class ContentBrief(SchemaBase):
    topic: str
    angle: str
    intent: SearchIntent
    keywords: KeywordSet
    audience: str = "general"
    voice: SiteVoice = SiteVoice.neutral
    outline: list[str] = Field(default_factory=list)  # e.g. ["H2: ...", "H2: ..."]
    product_slots: dict[str, list[str]] = Field(default_factory=dict)  # section -> product_ids
