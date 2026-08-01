import pytest

from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret")

    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_product_audit_returns_codes_not_sensitive_content():
    product = {"id": "gid://shopify/Product/1", "title": "P", "handle": "p", "status": "ACTIVE", "vendor": "", "productType": "", "descriptionHtml": "", "category": None, "seo": {"title": "", "description": ""}, "featuredMedia": None, "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/2", "title": "Default", "sku": "", "barcode": None, "price": "10.00", "inventoryQuantity": 0, "inventoryItem": {"tracked": True}}]}}
    response = {"data": {"products": {"edges": [{"cursor": "c", "node": product}], "pageInfo": {"hasNextPage": False, "endCursor": "c"}}}}
    result = await ShopifyOperations(SequenceClient([response])).audit_product_data({"first": 10})
    assert result["summary"]["productsWithIssues"] == 1
    assert "VARIANT_MISSING_SKU" in result["items"][0]["issues"]
    assert "descriptionHtml" not in result["items"][0]


@pytest.mark.asyncio
async def test_low_stock_builds_bounded_shopify_filter():
    response = {"data": {"productVariants": {"edges": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}
    client = SequenceClient([response])
    result = await ShopifyOperations(client).list_low_stock_variants({"threshold": 4, "locationId": "gid://shopify/Location/12"})
    assert client.calls[0][1]["query"] == "inventory_quantity:<=4 AND location_id:12"
    assert result["threshold"] == 4


@pytest.mark.asyncio
async def test_order_360_stops_when_order_does_not_exist():
    response = {"data": {"order": None}}
    client = SequenceClient([response])
    result = await ShopifyOperations(client).get_order_360({"id": "gid://shopify/Order/1"})
    assert result["order"] is None
    assert len(client.calls) == 1
