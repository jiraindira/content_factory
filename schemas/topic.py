from pydantic import BaseModel, Field
from typing import Literal


class TopicInput(BaseModel):
    current_date: str = Field(..., description="ISO date, e.g. 2025-11-15")
    region: str = Field(..., description="Target market region, e.g. US, UK")


class TopicOutput(BaseModel):
    topic: str = Field(..., description="Blog topic, human-readable")
    audience: str = Field(..., description="Primary audience segment")
    seasonality_score: float = Field(..., ge=0, le=1)
    search_intent: Literal["commercial", "informational"]
    rationale: str = Field(..., description="Why this topic is timely and valuable")
