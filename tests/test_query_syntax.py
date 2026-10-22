from shopify_mcp.operations import DISCOUNT_CODE_FRAGMENTS


def test_discount_code_fragments_have_balanced_braces():
    assert DISCOUNT_CODE_FRAGMENTS.count("{") == DISCOUNT_CODE_FRAGMENTS.count("}")


def test_automatic_discount_fragments_have_balanced_braces():
    from shopify_mcp.operations import AUTOMATIC_DISCOUNT_FRAGMENTS
    assert AUTOMATIC_DISCOUNT_FRAGMENTS.count("{") == AUTOMATIC_DISCOUNT_FRAGMENTS.count("}")
