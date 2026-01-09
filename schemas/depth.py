from pydantic import Field
from schemas.base import SchemaBase


class ExpansionModuleSpec(SchemaBase):
    """
    A requested "module" to add to the post, e.g. FAQ, buyer's guide, etc.
    """
    name: str = Field(..., description="Module identifier, e.g. 'how_we_chose', 'buyers_guide', 'faqs'")
    enabled: bool = Field(True, description="Whether to include this module")
    max_words: int = Field(250, ge=50, le=2000, description="Soft cap for the module content")
    notes: str = Field("", description="Optional extra instructions for the module")


class DepthExpansionInput(SchemaBase):
    """
    Input for DepthExpansionAgent.

    The agent takes an existing draft markdown and expands it by adding useful sections
    and enriching existing ones, while keeping the content grounded and non-fluffy.
    """
    topic: str = Field(..., description="Post topic")
    primary_keyword: str = Field(..., description="Primary keyword for the post")
    secondary_keywords: list[str] = Field(default_factory=list, description="Secondary/related keywords")

    title: str = Field(..., description="Final chosen title")
    slug: str = Field(..., description="Post slug")

    draft_markdown: str = Field(..., description="Existing draft markdown to expand")

    # Optional structured inputs that help expansion stay grounded
    products: list[dict] = Field(default_factory=list, description="List of product dicts (JSON-safe)")
    outline: list[str] = Field(default_factory=list, description="Target outline headings, e.g. ['H2: ...']")
    faqs: list[str] = Field(default_factory=list, description="FAQ questions to include if FAQ module enabled")

    # Controls
    target_word_count: int = Field(1400, ge=500, le=6000, description="Desired final word count (best effort)")
    max_added_words: int = Field(1200, ge=100, le=6000, description="Maximum words to add (best effort)")
    voice: str = Field("neutral", description="Voice style label")

    # Which modules to add (and how)
    modules: list[ExpansionModuleSpec] = Field(
        default_factory=lambda: [
            ExpansionModuleSpec(name="quick_picks", max_words=220),
            ExpansionModuleSpec(name="how_we_chose", max_words=220),
            ExpansionModuleSpec(name="buyers_guide", max_words=450),
            ExpansionModuleSpec(name="faqs", max_words=420),
            ExpansionModuleSpec(name="alternatives", max_words=280),
            ExpansionModuleSpec(name="care_and_maintenance", max_words=280),
        ],
        description="Expansion modules to apply in order",
    )

    # Guardrails
    forbid_claims_of_testing: bool = Field(
        True, description="Avoid implying hands-on testing unless explicitly provided"
    )
    allow_new_sections: bool = Field(
        True, description="Allow agent to append new sections even if not in outline"
    )

    # IMPORTANT: Your Astro site renders product cards from frontmatter.
    # Keep this False so the agent doesn't duplicate product lists in the markdown body.
    render_products_in_body: bool = Field(
        False,
        description="Whether to render product blocks in markdown body (default False for Astro cards).",
    )


class AppliedModule(SchemaBase):
    name: str = Field(..., description="Module name applied")
    added_words_estimate: int = Field(..., ge=0, description="Approx words added by this module")
    notes: str = Field("", description="What was added/changed")


class DepthExpansionOutput(SchemaBase):
    expanded_markdown: str = Field(..., description="Expanded markdown output")
    applied_modules: list[AppliedModule] = Field(default_factory=list, description="Modules applied and summaries")
    word_count_before: int = Field(..., ge=0, description="Approx word count before expansion")
    word_count_after: int = Field(..., ge=0, description="Approx word count after expansion")
