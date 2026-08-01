import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    async def graphql(self, query, variables=None): self.calls.append((query, variables)); return self.responses.pop(0)


def preview(currency="BRL", current=None):
    return {"data": {"priceList": {"id": "gid://shopify/PriceList/1", "name": "BR", "currency": currency, "fixedPricesCount": 1 if current else 0, "catalog": {"id": "gid://shopify/MarketCatalog/3", "title": "BR"}, "parent": None, "price0": {"nodes": [current] if current else []}}, "nodes": [{"id": "gid://shopify/ProductVariant/2", "title": "M", "product": {"id": "gid://shopify/Product/4", "title": "P"}, "inventoryItem": {"sku": "SKU"}}]}}


@pytest.mark.asyncio
async def test_fixed_price_rejects_currency_mismatch():
    request = {"priceListId": "gid://shopify/PriceList/1", "prices": [{"variantId": "gid://shopify/ProductVariant/2", "price": {"amount": "10.00", "currencyCode": "USD"}}]}
    with pytest.raises(ShopifyError, match="moeda"):
        await ShopifyOperations(SequenceClient([preview()])).prepare_fixed_prices_add(request)


@pytest.mark.asyncio
async def test_fixed_price_add_reports_replacement_and_binds_money_strings():
    current = {"price": {"amount": "9.00", "currencyCode": "BRL"}, "compareAtPrice": None, "originType": "FIXED", "variant": {"id": "gid://shopify/ProductVariant/2"}}
    payload = {"data": {"priceListFixedPricesAdd": {"prices": [], "userErrors": []}}}
    client = SequenceClient([preview(current=current), payload]); ops = ShopifyOperations(client)
    request = {"priceListId": "gid://shopify/PriceList/1", "prices": [{"variantId": "gid://shopify/ProductVariant/2", "price": {"amount": "10.00", "currencyCode": "BRL"}}]}
    proposal = await ops.prepare_fixed_prices_add(request)
    assert proposal["willReplaceExisting"] == 1
    await ops.fixed_prices_add({**request, "confirmationToken": proposal["confirmationToken"]})
    assert client.calls[-1][1] == request


@pytest.mark.asyncio
async def test_fixed_price_delete_previews_fallback():
    current = {"price": {"amount": "9.00", "currencyCode": "BRL"}, "compareAtPrice": None, "originType": "FIXED", "variant": {"id": "gid://shopify/ProductVariant/2"}}
    ops = ShopifyOperations(SequenceClient([preview(current=current)]))
    proposal = await ops.prepare_fixed_prices_delete({"priceListId": "gid://shopify/PriceList/1", "variantIds": ["gid://shopify/ProductVariant/2"]})
    assert proposal["willDelete"] == 1
    assert "ajuste padrão" in proposal["warnings"][0]
