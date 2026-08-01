import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_variant_create_preview_warns_for_removal_strategy_and_applies():
    client = SequenceClient([
        {"data": {"product": {"id": "gid://shopify/Product/1", "title": "Sheet", "handle": "sheet", "options": [], "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/1", "title": "Default Title"}]}}}},
        {"data": {"productVariantsBulkCreate": {"product": {"id": "gid://shopify/Product/1"}, "productVariants": [{"id": "gid://shopify/ProductVariant/2"}], "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    variants = [{"optionValues": [{"name": "Queen", "optionName": "Size"}], "price": "199.90", "inventoryItem": {"sku": "SHEET-Q"}}]
    preview = await ops.prepare_variants_bulk_create({"productId": "gid://shopify/Product/1", "strategy": "REMOVE_STANDALONE_VARIANT", "variants": variants})
    assert preview["willCreate"] == 1
    assert preview["warnings"]
    result = await ops.variants_bulk_create({"productId": "gid://shopify/Product/1", "strategy": "REMOVE_STANDALONE_VARIANT", "variants": variants, "confirmationToken": preview["confirmationToken"]})
    assert result["summary"] == {"requested": 1, "created": 1}


@pytest.mark.asyncio
async def test_variant_update_rejects_wrong_product_before_token():
    client = SequenceClient([{ "data": {"nodes": [{"id": "gid://shopify/ProductVariant/2", "product": {"id": "gid://shopify/Product/OTHER"}}]}}])
    ops = ShopifyOperations(client)
    with pytest.raises(ShopifyError, match="não pertencem"):
        await ops.prepare_variants_bulk_update({"productId": "gid://shopify/Product/1", "variants": [{"id": "gid://shopify/ProductVariant/2", "price": "10.00"}]})


@pytest.mark.asyncio
async def test_variant_update_is_atomic():
    client = SequenceClient([
        {"data": {"nodes": [{"id": "gid://shopify/ProductVariant/2", "product": {"id": "gid://shopify/Product/1"}, "price": "9.00"}]}},
        {"data": {"productVariantsBulkUpdate": {"product": {"id": "gid://shopify/Product/1"}, "productVariants": [{"id": "gid://shopify/ProductVariant/2", "price": "10.00"}], "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    variants = [{"id": "gid://shopify/ProductVariant/2", "price": "10.00"}]
    preview = await ops.prepare_variants_bulk_update({"productId": "gid://shopify/Product/1", "variants": variants})
    result = await ops.variants_bulk_update({"productId": "gid://shopify/Product/1", "variants": variants, "confirmationToken": preview["confirmationToken"]})
    assert result["summary"]["atomic"] is True
    assert "allowPartialUpdates:false" in client.calls[-1][0]


@pytest.mark.asyncio
async def test_variant_update_rejects_duplicate_ids_without_api_call():
    client = SequenceClient([])
    variants = [{"id": "gid://shopify/ProductVariant/2", "price": "10.00"}, {"id": "gid://shopify/ProductVariant/2", "price": "11.00"}]
    with pytest.raises(ValueError, match="apenas uma vez"):
        await ShopifyOperations(client).prepare_variants_bulk_update({"productId": "gid://shopify/Product/1", "variants": variants})
    assert client.calls == []


@pytest.mark.asyncio
async def test_variant_update_rejects_empty_change():
    client = SequenceClient([])
    with pytest.raises(ValueError, match="ao menos um campo"):
        await ShopifyOperations(client).prepare_variants_bulk_update({"productId": "gid://shopify/Product/1", "variants": [{"id": "gid://shopify/ProductVariant/2"}]})
