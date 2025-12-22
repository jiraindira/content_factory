import json
from pathlib import Path
from openai import OpenAI
from schemas.topic import TopicInput, TopicOutput
from config import OPENAI_API_KEY, MODEL_REASONING

PROMPT_PATH = Path("prompts/topic_selection.txt")


class TopicSelectionAgent:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.prompt_template = PROMPT_PATH.read_text()

    def run(self, input_data: TopicInput) -> TopicOutput:
        prompt = (
            self.prompt_template
            .replace("{{current_date}}", input_data.current_date)
            .replace("{{region}}", input_data.region)
        )

        response = self.client.responses.create(
            model=MODEL_REASONING,
            input=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        raw_output = response.output_text.strip()

        # Remove Markdown code fences if present
        if raw_output.startswith("```") and raw_output.endswith("```"):
            lines = raw_output.splitlines()
            if len(lines) >= 3:
                raw_output = "\n".join(lines[1:-1])

        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Topic Agent:\n{raw_output}") from e

        return TopicOutput(**parsed)
