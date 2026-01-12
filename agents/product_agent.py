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

Use this content brief (NOT a blog title):
- Topic label: {topic.topic}
- Audience: {topic.audience}

Task:
Generate a list of 5–10 Amazon-relevant product ideas that match the topic label and audience.

Rules:
- Products should be specific items someone could actually buy (not vague categories).
- Do NOT invent affiliate links, prices, ratings, or review counts. If unknown, use null.
- Provide a short Amazon search query we can use to look up the real product later.

Respond ONLY in JSON with a top-level "products" list like this:

{{
  "products": [
    {{
      "title": "...",
      "amazon_search_query": "...",
      "url": null,
      "price": null,
      "rating": null,
      "reviews_count": null,
      "description": "1–2 sentences"
    }}
  ]
}}
"""

        response = self.client.responses.create(
            model=MODEL_REASONING,
            input=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        raw_output = response.output_text.strip()

        # Remove Markdown code fences if present
        if raw_output.startswith("```"):
            lines = raw_output.splitlines()
            raw_output = "\n".join(line for line in lines if not line.strip().startswith("```")).strip()

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from Product Agent:\n{raw_output}") from e

        products = [Product(**p) for p in data.get("products", [])]
        return products
