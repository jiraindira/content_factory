from enum import Enum
from pydantic import Field
from .base import SchemaBase

class SearchIntent(str, Enum):
    informational = "informational"
    commercial = "commercial"
    transactional = "transactional"

class Language(str, Enum):
    en = "en"

class SiteVoice(str, Enum):
    neutral = "neutral"
    wirecutterish = "wirecutterish"
    nerdwalletish = "nerdwalletish"

class KeywordSet(SchemaBase):
    primary: str
    secondary: list[str] = Field(default_factory=list)
