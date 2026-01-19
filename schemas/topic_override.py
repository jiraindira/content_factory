from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


TopicCategory = Literal["home", "travel", "gadgets", "pets", "kids", "health"]


class TopicOverride(BaseModel):
    date: str = Field(..., description="ISO date YYYY-MM-DD (UTC).")
    topic: str
    category: TopicCategory
    audience: str


class TopicOverridesFile(BaseModel):
    overrides: list[TopicOverride] = Field(default_factory=list)
