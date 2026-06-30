from __future__ import annotations

import json
import os
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Sonnet 4.6 is the production workhorse — strong long-form writing at a good price.
# Override per-deployment with ANTHROPIC_MODEL (e.g. claude-opus-4-8 for a premium tier).
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Articles can run ~1,200 words; give comfortable headroom for the JSON wrapper too.
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "8192"))


def _first_text(response: anthropic.types.Message) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return (block.text or "").strip()
    return ""


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    return text


class ClaudeJsonLLM:
    """
    JSON-only LLM wrapper for Anthropic Claude.
    Matches the same interface as OpenAIJsonLLM so callers are interchangeable.

    When a JSON schema is supplied, uses structured outputs for a guaranteed-valid
    response; otherwise falls back to prompt-instructed JSON + fence stripping.

    A `reference_document` (e.g. a client's book) can be passed and is prompt-cached,
    so repeated generations grounded in the same source only pay ~10% on cache reads.
    """

    def __init__(self, *, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or DEFAULT_MODEL
        # max_retries=4: the SDK auto-retries connection errors and 429/5xx with
        # exponential backoff. Bumped from the default of 2 because the GitHub
        # Actions scheduler occasionally hits transient connection blips to the API.
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            max_retries=4,
        )

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        reference_document: str | None = None,
    ) -> dict[str, Any]:
        # System prompt: stable core first (cacheable), then the JSON instruction.
        system_blocks: list[dict[str, Any]] = [{"type": "text", "text": system}]

        # Ground generation in a large reference (book/manuscript), cached for cheap reuse.
        if reference_document:
            system_blocks.append({
                "type": "text",
                "text": (
                    "Use the following source material as the factual and conceptual basis "
                    "for your writing. Draw on its frameworks, language, and ideas — do not "
                    "contradict it or invent concepts that aren't grounded in it.\n\n"
                    f"<source_material>\n{reference_document}\n</source_material>"
                ),
                "cache_control": {"type": "ephemeral"},
            })

        base_kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": system_blocks,
            "messages": [{"role": "user", "content": user}],
        }

        text = ""

        # 1) Preferred: structured outputs (guaranteed valid JSON) when a schema is given.
        if schema is not None:
            try:
                resp = self.client.messages.create(
                    **base_kwargs,
                    output_config={"format": {"type": "json_schema", "schema": schema}},
                )
                text = _first_text(resp)
            except (TypeError, anthropic.BadRequestError):
                # SDK/model doesn't accept output_config — fall through to prompt-based JSON.
                text = ""

        # 2) Fallback: prompt-instructed JSON.
        if not text:
            sys_with_json = list(system_blocks)
            sys_with_json[0] = {
                **system_blocks[0],
                "text": system_blocks[0]["text"]
                + "\n\nRespond with valid JSON only. No prose, no markdown fences.",
            }
            resp = self.client.messages.create(
                **{**base_kwargs, "system": sys_with_json},
            )
            text = _strip_fences(_first_text(resp))

        if not text:
            raise RuntimeError("Claude returned an empty response; cannot parse JSON.")

        try:
            return json.loads(text)
        except Exception as e:
            raise RuntimeError(f"Claude did not return valid JSON. Error={e}. Raw={text[:500]}") from e
