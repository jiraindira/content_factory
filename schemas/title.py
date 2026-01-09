from pydantic import Field
from schemas.base import SchemaBase


class TitleOptimizationInput(SchemaBase):
    """
    Input for TitleOptimizationAgent.

    Notes:
    - existing_titles is used to penalize similarity and avoid repeating your current patterns.
    - banned_starts helps prevent monoculture like "Top Cozy ...".
    """
    topic: str = Field(..., description="High-level topic for the blog post")
    primary_keyword: str = Field(..., description="Primary SEO keyword")
    secondary_keywords: list[str] = Field(default_factory=list, description="Secondary/related keywords")

    existing_titles: list[str] = Field(default_factory=list, description="Previously used titles to avoid repeating")

    # Tuning knobs
    num_candidates: int = Field(40, ge=10, le=100, description="How many title candidates to generate")
    return_top_n: int = Field(3, ge=1, le=10, description="How many top titles to return")

    banned_starts: list[str] = Field(
        default_factory=lambda: ["Top", "Top Cozy", "Top cosy", "Best", "Best Cozy", "Best cosy"],
        description="Title prefixes that are overused or undesirable"
    )

    # Optional: site voice label (simple string for now; upgrade to Enum later if you want)
    voice: str = Field("neutral", description="Voice style: neutral, wirecutterish, nerdwalletish, etc.")


class TitleCandidate(SchemaBase):
    title: str = Field(..., description="The proposed title")
    archetype: str = Field(..., description="Which template/archetype produced this title")
    score: float = Field(..., ge=0, le=100, description="Overall score (0-100)")
    reasons: list[str] = Field(default_factory=list, description="Short reasons explaining the score")


class TitleOptimizationOutput(SchemaBase):
    selected: list[TitleCandidate] = Field(..., description="Top-N titles selected")
    candidates: list[TitleCandidate] = Field(..., description="All generated title candidates (scored)")
