from pydantic import HttpUrl, Field
from schemas.base import SchemaBase

class Product(SchemaBase):
    title: str = Field(..., description="Product name/title")
    url: HttpUrl = Field(..., description="Amazon referral link")
    price: str = Field(..., description="Price if available")
    rating: float = Field(..., ge=0, le=5, description="Average rating")
    reviews_count: int = Field(..., description="Number of reviews")
    description: str = Field(..., description="Short product description")
