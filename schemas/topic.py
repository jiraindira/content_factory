from pydantic import BaseModel
from schemas.category import Category


class TopicInput(BaseModel):
    current_date: str
    region: str


class TopicOutput(BaseModel):
    topic: str
    category: Category
    audience: str
    seasonality_score: float
    search_intent: str
    rationale: str
