from jsonschema import Draft202012Validator
import pytest
from jsonschema.exceptions import ValidationError

from shopify_mcp.catalog import DEFINITIONS, enabled_definitions


def names(profile, writes):
    return {item.tool.name for item in enabled_definitions(profile, writes)}


def test_readonly_never_exposes_mutations():
    assert len(names("readonly", False)) == 73
    assert all(not item.write for item in enabled_definitions("readonly", False))
    assert all(not item.write for item in enabled_definitions("readonly", True))


def test_catalog_exposes_writes_only_when_globally_enabled():
    assert "shopify_update_product_seo" not in names("catalog", False)
    assert "shopify_update_product_seo" in names("catalog", True)
    assert "shopify_create_product" in names("catalog", True)


def test_product_create_requires_title_and_rejects_unknown_fields():
    definition = next(item.tool for item in DEFINITIONS if item.tool.name == "shopify_prepare_product_create")
    validator = Draft202012Validator(definition.inputSchema)
    with pytest.raises(ValidationError):
        validator.validate({"vendor": "MOOUI"})
    with pytest.raises(ValidationError):
        validator.validate({"title": "Sheet", "variants": []})


def test_variant_money_rejects_float_and_excess_precision():
    definition = next(item.tool for item in DEFINITIONS if item.tool.name == "shopify_prepare_variants_bulk_create")
    base = {"productId": "gid://shopify/Product/1", "strategy": "PRESERVE_STANDALONE_VARIANT", "variants": [{"optionValues": [{"name": "Queen", "optionName": "Size"}]}]}
    validator = Draft202012Validator(definition.inputSchema)
    validator.validate(base)
    for invalid in (10.1, "10.999"):
        payload = {**base, "variants": [{**base["variants"][0], "price": invalid}]}
        with pytest.raises(ValidationError):
            validator.validate(payload)


def test_every_tool_has_valid_schema_and_annotation():
    for definition in DEFINITIONS:
        Draft202012Validator.check_schema(definition.tool.inputSchema)
        assert definition.tool.annotations is not None
        assert definition.tool.annotations.readOnlyHint is (not definition.write)


def test_gid_and_additional_properties_are_validated():
    product = next(item.tool for item in DEFINITIONS if item.tool.name == "shopify_get_product")
    validator = Draft202012Validator(product.inputSchema)
    with pytest.raises(ValidationError):
        validator.validate({"id": "https://attacker.example/product/1"})
    with pytest.raises(ValidationError):
        validator.validate({"id": "gid://shopify/Product/1", "unexpected": True})


def test_duplicate_tags_are_rejected():
    add_tags = next(item.tool for item in DEFINITIONS if item.tool.name == "shopify_add_tags")
    with pytest.raises(ValidationError):
        Draft202012Validator(add_tags.inputSchema).validate({
            "id": "gid://shopify/Product/1", "tags": ["sale", "sale"], "confirmationToken": "x" * 40
        })
