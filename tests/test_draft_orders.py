import pytest

from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", financial_limits_brl=(("complete_draft", "100.00"),))

    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


# Schema 2026-07: bundle nas draft queries vem no campo aninhado `components`
# (não `bundleComponents`, e NÃO há flattenComponents em draftOrder). requiresComponents
# vive em ProductVariant. Ver CHANGELOG.


@pytest.mark.asyncio
async def test_draft_order_query_requests_components():
    client = SequenceClient([{"data": {"draftOrder": {"id": "gid://shopify/DraftOrder/1", "lineItems": {"nodes": []}}}}])
    await ShopifyOperations(client).get_draft_order({"id": "gid://shopify/DraftOrder/1"})
    assert "components" in client.calls[0][0]
    assert "requiresComponents" in client.calls[0][0]


@pytest.mark.asyncio
async def test_draft_order_calculate_requests_components():
    node = {"id": "gid://shopify/ProductVariant/1", "title": "U", "sku": "1",
            "availableForSale": True, "inventoryQuantity": 5,
            "product": {"id": "gid://shopify/Product/1", "title": "x", "status": "ACTIVE"}}
    response = {"data": {"draftOrderCalculate": {"calculatedDraftOrder": {"lineItems": []}, "userErrors": []},
                         "nodes": [node]}}
    client = SequenceClient([response])
    await ShopifyOperations(client).prepare_draft_order_create({"lineItems": [{"variantId": "gid://shopify/ProductVariant/1"}]})
    assert "components" in client.calls[0][0]
    assert "requiresComponents" in client.calls[0][0]


@pytest.mark.asyncio
async def test_draft_order_complete_preview_requests_components():
    draft = {"id": "gid://shopify/DraftOrder/1", "name": "#D1", "status": "OPEN",
             "totalPriceSet": {"shopMoney": {"amount": "100.00", "currencyCode": "BRL"}},
             "order": None, "lineItems": {"nodes": []}}
    client = SequenceClient([{"data": {"draftOrder": draft}}])
    await ShopifyOperations(client).prepare_draft_order_complete({"id": "gid://shopify/DraftOrder/1"})
    assert "components" in client.calls[0][0]
    assert "requiresComponents" in client.calls[0][0]
