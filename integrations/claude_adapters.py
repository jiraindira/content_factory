from __future__ import annotations

import json
import os
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")


class ClaudeJsonLLM:
    """
    JSON-only LLM wrapper for Anthropic Claude.
    Matches the same interface as OpenAIJsonLLM so callers are interchangeable.
    """

    def __init__(self, *, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or DEFAULT_MODEL
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system + "\n\nYou must respond with valid JSON only. No prose, no markdown fences.",
            messages=[{"role": "user", "content": user}],
        )

        text = response.content[0].text.strip()

        # Strip markdown code fences if the model added them anyway
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines
                if not line.startswith("```")
            ).strip()

        try:
            return json.loads(text)
        except Exception as e:
            raise RuntimeError(f"Claude did not return valid JSON. Error={e}. Raw={text[:500]}") from e
