from __future__ import annotations

from pathlib import Path

from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


def test_the_product_wheel_brand_yaml_is_valid() -> None:
    repo = Path(__file__).resolve().parents[1]
    brand = load_brand_profile(repo / "content_factory" / "brands" / "the_product_wheel.yaml")
    assert brand.brand_id == "the_product_wheel"


def test_the_product_wheel_request_is_valid_against_brand() -> None:
    repo = Path(__file__).resolve().parents[1]
    brand = load_brand_profile(repo / "content_factory" / "brands" / "the_product_wheel.yaml")
    req = load_content_request(repo / "content_factory" / "requests" / "the_product_wheel_2026-02-16.yaml")
    validate_request_against_brand(brand=brand, request=req)
