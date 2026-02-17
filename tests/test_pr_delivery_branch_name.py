from content_factory.pr_delivery import default_branch_name


def test_default_branch_name_sanitizes_components() -> None:
    b = default_branch_name(brand_id="the product wheel", run_id="tpw_smoke@amzn")
    assert b == "content/the-product-wheel/tpw_smoke-amzn"
