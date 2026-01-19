from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


PostFormatId = Literal["top_picks", "deep_dive", "use_case_kit"]


class PostFormatSpec(BaseModel):
    id: PostFormatId
    # number of products to request
    picks_min: int = Field(..., ge=1)
    picks_max: int = Field(..., ge=1)

    # DepthExpansion modules configuration
    max_words_intro: int = 140
    max_words_how_we_chose: int = 170
    max_words_alternatives: int = 220
    max_words_product_writeups: int = 900

    def pick_count_target(self) -> int:
        # deterministic “middle” pick count
        return (self.picks_min + self.picks_max) // 2
