from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RewriteMode = Literal["repair", "upgrade", "preserve"]


class ExpansionModuleSpec(BaseModel):
    """
    A single expansion module the DepthExpansionAgent may apply.

    rewrite_mode:
      - None: inherit from DepthExpansionInput.rewrite_mode
      - "repair": only rewrite existing sections if they look agent-y / internal
      - "upgrade": rewrite existing sections to match the style profile voice
      - "preserve": never rewrite existing sections (only add missing ones)
    """

    name: str = Field(..., description="Module name")
    enabled: bool = Field(True, description="Whether module is active")
    max_words: int = Field(220, ge=20, description="Clamp module output to this many words")
    notes: str = Field("", description="Free-form notes")
    rewrite_mode: Optional[RewriteMode] = Field(
        None,
        description="Override the global rewrite mode for this module",
    )


class AppliedModule(BaseModel):
    name: str
    added_words_estimate: int = 0
    notes: str = ""


class DepthExpansionInput(BaseModel):
    """
    Input to DepthExpansionAgent.

    draft_markdown:
      A markdown doc that typically contains frontmatter and may contain some sections like
      '## Why this list'. The agent will add/replace sections based on modules + style profile.

    rewrite_mode:
      - repair: conservative; only rewrites content that looks like internal agent rationale
      - upgrade: editorial; rewrites existing bland sections into the site voice
      - preserve: hands-off; only adds missing sections
    """

    draft_markdown: str = Field(..., description="Existing markdown draft (frontmatter + optional sections).")

    products: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of product dicts (title, url, price, rating, reviews_count, description).",
    )

    modules: List[ExpansionModuleSpec] = Field(
        default_factory=list,
        description="Ordered list of modules to apply.",
    )

    max_added_words: int = Field(
        900,
        ge=0,
        description="Stop expanding once we exceed this many added words vs original.",
    )

    voice: str = Field("neutral", description="Optional voice selector passed to style system.")

    faqs: List[str] = Field(default_factory=list, description="Optional FAQ questions to use.")
    forbid_claims_of_testing: bool = Field(
        True,
        description="If True, add a note that we did not do hands-on testing (where applicable).",
    )

    rewrite_mode: RewriteMode = Field(
        "repair",
        description="Global rewrite mode: repair | upgrade | preserve",
    )


class DepthExpansionOutput(BaseModel):
    expanded_markdown: str
    applied_modules: List[AppliedModule]

    word_count_before: int
    word_count_after: int

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
