from lib.pick_image_enrichment import _extract_amazon_product_image


def test_extract_amazon_product_image_prefers_data_old_hires() -> None:
    html = (
        '<img id="landingImage" data-old-hires="https://example.com/hires.jpg" '
        'data-a-dynamic-image="{&quot;https://example.com/other.jpg&quot;:[10,10]}" />'
    )
    assert _extract_amazon_product_image(html) == "https://example.com/hires.jpg"


def test_extract_amazon_product_image_dynamic_image_largest_area_and_unescape() -> None:
    html = (
        '<div data-a-dynamic-image="{'
        '&quot;https://example.com/small.jpg&quot;:[100,50],'
        '&quot;https://example.com/big.jpg&quot;:[1200,800]'
        '}" ></div>'
    )
    assert _extract_amazon_product_image(html) == "https://example.com/big.jpg"


def test_extract_amazon_product_image_dynamic_image_any_tag() -> None:
    html = (
        '<span data-a-dynamic-image="{&quot;https://example.com/a.jpg&quot;:[200,200]}" ></span>'
    )
    assert _extract_amazon_product_image(html) == "https://example.com/a.jpg"


def test_extract_amazon_product_image_landing_image_src_fallback() -> None:
    html = '<img id="landingImage" src="https://example.com/src.jpg" />'
    assert _extract_amazon_product_image(html) == "https://example.com/src.jpg"


def test_extract_amazon_product_image_landing_image_data_src_fallback() -> None:
    html = '<img id="landingImage" data-src="https://example.com/datasrc.jpg" />'
    assert _extract_amazon_product_image(html) == "https://example.com/datasrc.jpg"


def test_extract_amazon_product_image_hires_unescapes_slashes() -> None:
    html = '"hiRes":"https:\\/\\/example.com\\/img.jpg"'
    assert _extract_amazon_product_image(html) == "https://example.com/img.jpg"
