from typing import Optional
from pydantic import Field, HttpUrl
from schemas.base import SchemaBase


class Product(SchemaBase):
    title: str = Field(..., description="Product name/title")

    # Used later to look up the real product on Amazon
    amazon_search_query: Optional[str] = Field(
        None,
        description="Search query to find this product on Amazon"
    )

    # Real commerce fields (not available at discovery time)
    url: Optional[HttpUrl] = Field(
        None,
        description="Amazon referral link (filled later)"
    )
    price: Optional[str] = Field(
        None,
        description="Price if available"
    )
    rating: Optional[float] = Field(
        None,
        ge=0,
        le=5,
        description="Average rating"
    )
    reviews_count: Optional[int] = Field(
        None,
        description="Number of reviews"
    )

    description: str = Field(..., description="Short product description")
