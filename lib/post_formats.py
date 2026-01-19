from __future__ import annotations

from schemas.post_format import PostFormatSpec, PostFormatId


def get_format_spec(format_id: PostFormatId) -> PostFormatSpec:
    if format_id == "top_picks":
        return PostFormatSpec(
            id="top_picks",
            picks_min=7,
            picks_max=9,
            max_words_intro=150,
            max_words_how_we_chose=170,
            max_words_alternatives=220,
            max_words_product_writeups=950,
        )

    if format_id == "deep_dive":
        # single product deep dive
        return PostFormatSpec(
            id="deep_dive",
            picks_min=1,
            picks_max=1,
            max_words_intro=170,
            max_words_how_we_chose=140,
            max_words_alternatives=220,
            max_words_product_writeups=800,
        )

    if format_id == "use_case_kit":
        # scenario-based kit list
        return PostFormatSpec(
            id="use_case_kit",
            picks_min=6,
            picks_max=10,
            max_words_intro=170,
            max_words_how_we_chose=160,
            max_words_alternatives=220,
            max_words_product_writeups=950,
        )

    raise ValueError(f"Unknown format_id: {format_id}")
