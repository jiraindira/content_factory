from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from content_factory.validation import (
    load_brand_profile,
    load_content_request,
    validate_request_against_brand,
)


def _write_yaml(tmpdir: Path, name: str, data: dict[str, Any]) -> Path:
    path = tmpdir / name
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    return path


class TestContentFactoryValidation(unittest.TestCase):
    def test_valid_examples(self) -> None:
        repo = Path(__file__).resolve().parents[1]

        brand = load_brand_profile(repo / "content_factory" / "brands" / "alisa_amouage.yaml")
        req = load_content_request(repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml")
        validate_request_against_brand(brand=brand, request=req)

        brand2 = load_brand_profile(repo / "content_factory" / "brands" / "everyday_buying_guide.yaml")
        req2 = load_content_request(repo / "content_factory" / "requests" / "everyday_buying_guide_2026-02-01.yaml")
        validate_request_against_brand(brand=brand2, request=req2)

    def test_past_publish_date_fails(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "alisa_amouage.yaml")

        req_data = yaml.safe_load((repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml").read_text(encoding="utf-8"))
        req_data["publish"]["publish_date"] = (date.today() - timedelta(days=1)).isoformat()

        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            req_path = _write_yaml(tmpdir, "req.yaml", req_data)
            req = load_content_request(req_path)
            with self.assertRaises(ValueError):
                validate_request_against_brand(brand=brand, request=req)

    def test_topic_not_in_allowlist_fails(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "alisa_amouage.yaml")

        req_data = yaml.safe_load((repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml").read_text(encoding="utf-8"))
        req_data["topic"]["value"] = "Not in allowlist"

        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            req_path = _write_yaml(tmpdir, "req.yaml", req_data)
            req = load_content_request(req_path)
            with self.assertRaises(ValueError):
                validate_request_against_brand(brand=brand, request=req)

    def test_product_form_requires_manual_list(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "everyday_buying_guide.yaml")

        req_data = yaml.safe_load(
            (repo / "content_factory" / "requests" / "everyday_buying_guide_2026-02-01.yaml").read_text(
                encoding="utf-8"
            )
        )
        req_data["products"]["mode"] = "none"
        req_data["products"]["items"] = []

        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            req_path = _write_yaml(tmpdir, "req.yaml", req_data)
            req = load_content_request(req_path)
            with self.assertRaises(ValueError):
                validate_request_against_brand(brand=brand, request=req)

    def test_thought_leadership_must_have_no_products(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand = load_brand_profile(repo / "content_factory" / "brands" / "alisa_amouage.yaml")

        req_data = yaml.safe_load((repo / "content_factory" / "requests" / "alisa_2026-02-01.yaml").read_text(encoding="utf-8"))
        req_data["products"]["mode"] = "manual_list"
        req_data["products"]["items"] = [
            {
                "pick_id": "x",
                "title": "Example",
                "url": "https://example.com",
            }
        ]

        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            req_path = _write_yaml(tmpdir, "req.yaml", req_data)
            req = load_content_request(req_path)
            with self.assertRaises(ValueError):
                validate_request_against_brand(brand=brand, request=req)

    def test_brand_sources_requirement_fails(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        brand_data = yaml.safe_load((repo / "content_factory" / "brands" / "alisa_amouage.yaml").read_text(encoding="utf-8"))
        # require homepage/linkedin, but provide only an unrelated purpose
        brand_data["brand_sources"]["sources"] = [
            {
                "source_id": "x",
                "kind": "url",
                "purpose": "other",
                "ref": "https://example.com",
            }
        ]

        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            brand_path = _write_yaml(tmpdir, "brand.yaml", brand_data)
            with self.assertRaises(Exception):
                load_brand_profile(brand_path)
