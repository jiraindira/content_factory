import json
import re
from pathlib import Path
from openai import OpenAI

from schemas.topic import TopicInput, TopicOutput
from memory.category_memory import CategoryMemory
from config import OPENAI_API_KEY, MODEL_REASONING

# ---- ADD SANITIZATION HELPERS HERE ----

BANNED_TITLE_TOKENS = [
    "top", "best", "ultimate", "must-have", "must have",
    "this season", "this season’s", "this season's",
    "what to buy", "worth buying", "explained", "guide",
    "kickstart", "goals",
]

def _sanitize_text(s: str) -> str:
    if not s:
        return s

    s = s.strip()

    # Remove leading hype words like "Top ..."
    s = re.sub(
        r"^(top|best|ultimate)\b[\s:,-]*",
        "",
        s,
        flags=re.IGNORECASE,
    )

    # Remove banned phrases anywhere
    for phrase in BANNED_TITLE_TOKENS:
        s = re.sub(
            rf"\b{re.escape(phrase)}\b",
            " ",
            s,
            flags=re.IGNORECASE,
        )

    # Collapse whitespace
    return " ".join(s.split())

def _sanitize_topic_payload(parsed: dict) -> dict:
    # Fields that should NEVER be headline-y
    for key in ("topic", "primary_keyword"):
        if isinstance(parsed.get(key), str):
            parsed[key] = _sanitize_text(parsed[key])

    if isinstance(parsed.get("secondary_keywords"), list):
        parsed["secondary_keywords"] = [
            _sanitize_text(x)
            for x in parsed["secondary_keywords"]
            if isinstance(x, str) and _sanitize_text(x)
        ]

    return parsed

# ---- EXISTING CONSTANT ----

PROMPT_PATH = Path("prompts/topic_selection.txt")


class TopicSelectionAgent:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
        self.memory = CategoryMemory()

    def run(self, input_data: TopicInput) -> TopicOutput:
        # Load recent categories for rotation enforcement
        recent_categories = ", ".join(self.memory.recent()) or "none"

        prompt = (
            self.prompt_template
            .replace("{{current_date}}", input_data.current_date)
            .replace("{{region}}", input_data.region)
            .replace("{{recent_categories}}", recent_categories)
        )

        response = self.client.responses.create(
            model=MODEL_REASONING,
            input=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        raw_output = response.output_text.strip()

        # Defensive cleanup: remove markdown code fences if the model adds them
        if raw_output.startswith("```"):
            lines = raw_output.splitlines()
            raw_output = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        try:
            parsed = json.loads(raw_output)
            parsed = _sanitize_topic_payload(parsed)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Topic Agent:\n{raw_output}") from e

        # Persist category to memory (THIS WAS THE BUG)
        self.memory.record(parsed["category"])

        return TopicOutput(**parsed)
