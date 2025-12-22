import json
from openai import OpenAI
from schemas.topic import TopicOutput
from schemas.product import Product
from config import OPENAI_API_KEY, MODEL_REASONING

class ProductDiscoveryAgent:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def run(self, topic: TopicOutput) -> list[Product]:
        prompt = f"""
        You are an expert affiliate marketer.
        Given the blog topic: "{topic.topic}" and audience: "{topic.audience}", 
        generate a list of 5-10 popular Amazon products relevant to this topic.
        Each product should include:
        - title
        - URL (affiliate link)
        - price
        - rating (0-5)
        - reviews_count (integer)
        - description (1-2 sentences)

        Respond ONLY in JSON, with a top-level "products" list like this:

        {{
          "products": [
            {{
              "title": "...",
              "url": "...",
              "price": "...",
              "rating": 4.5,
              "reviews_count": 300,
              "description": "..."
            }}
          ]
        }}
        """

        response = self.client.responses.create(
            model=MODEL_REASONING,
            input=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        raw_output = response.output_text.strip()

        # Remove Markdown code fences if present
        if raw_output.startswith("```") and raw_output.endswith("```"):
            lines = raw_output.splitlines()
            if len(lines) >= 3:
                raw_output = "\n".join(lines[1:-1])

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Product Agent:\n{raw_output}") from e

        products = [Product(**p) for p in data.get("products", [])]
        return products
