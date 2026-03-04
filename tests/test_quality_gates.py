
import unittest
from pathlib import Path
from content_factory.cli import run_pipeline
from content_factory.validation import load_brand_profile, load_content_request
from agents.preflight_qa_agent import _extract_pick_blocks_from_markdown

class TestQualityGates(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parents[1]
        self.brand_path = self.repo / "content_factory" / "brands" / "the_product_wheel.yaml"
        self.request_path = self.repo / "content_factory" / "requests" / "the_product_wheel_manual_import.yaml"

    def test_editorial_required(self):
        # Should fail if OPENAI_API_KEY is not set
        import os
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with self.assertRaises(Exception):
                run_pipeline(self.brand_path, self.request_path)
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key


    def _generate_output(self):
        # Generate output using the pipeline (requires OPENAI_API_KEY for full editorial)
        out_path = run_pipeline(self.brand_path, self.request_path)
        with open(out_path, encoding="utf-8") as f:
            return f.read()

    def test_no_closing_header(self):
        md = self._generate_output()
        self.assertNotIn("## Closing", md, "Output should not contain a '## Closing' header")


    def test_pick_bodies_no_rating_review(self):
        md = self._generate_output()
        picks = _extract_pick_blocks_from_markdown(md)
        forbidden = ["rating", "review", "stars"]
        for pick in picks:
            body = pick.get("body", "") if isinstance(pick, dict) else ""
            for word in forbidden:
                self.assertNotIn(word, body.lower(), f"Pick body should not mention '{word}'")


    def test_pick_bodies_skip_it_if(self):
        md = self._generate_output()
        picks = _extract_pick_blocks_from_markdown(md)
        for pick in picks:
            body = pick.get("body", "") if isinstance(pick, dict) else ""
            self.assertIn("skip it if", body.lower(), "Each pick body should contain 'Skip it if'")

    def test_fixture_mode_passes(self):
        # Simulate a CI run with a fixture output (no API key required)
        md = self._generate_output()
        self.assertIn("title:", md)
        self.assertNotIn("## Closing", md)

    def test_structural_contracts(self):
        md = self._generate_output()
        # Check for required frontmatter fields
        required = ["title:", "description:", "publishedAt:", "categories:", "products:"]
        for field in required:
            self.assertIn(field, md, f"Frontmatter missing required field: {field}")

if __name__ == "__main__":
    unittest.main()
