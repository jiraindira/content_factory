import json
from pathlib import Path
from openai import OpenAI

from schemas.topic import TopicInput, TopicOutput
from memory.category_memory import CategoryMemory
from config import OPENAI_API_KEY, MODEL_REASONING

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
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Topic Agent:\n{raw_output}") from e

        # Persist category to memory (THIS WAS THE BUG)
        self.memory.record(parsed["category"])

        return TopicOutput(**parsed)
