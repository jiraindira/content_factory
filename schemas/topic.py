from schemas.base import SchemaBase
from schemas.category import Category


class TopicInput(SchemaBase):
    current_date: str
    region: str


class TopicOutput(SchemaBase):
    topic: str
    category: Category
    audience: str
    seasonality_score: float
    search_intent: str
    rationale: str
