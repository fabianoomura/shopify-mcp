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
async def test_get_product_variant_exposes_bundle_components():
    variant = {
        "id": "gid://shopify/ProductVariant/1", "sku": None, "requiresComponents": True,
        "productVariantComponents": {"nodes": [
            {"id": "gid://shopify/ProductVariantComponent/9", "quantity": 1,
             "productVariant": {"id": "gid://shopify/ProductVariant/2", "title": "U", "sku": "14771", "price": "67.00",
                                "product": {"id": "gid://shopify/Product/20", "title": "Fronha Bebê - Listrado Bolinhas", "handle": "fronha-bebe-listrado-bolinhas"}}},
            {"id": "gid://shopify/ProductVariantComponent/10", "quantity": 1,
             "productVariant": {"id": "gid://shopify/ProductVariant/3", "title": "BERCO", "sku": "14757", "price": "197.00",
                                "product": {"id": "gid://shopify/Product/21", "title": "Lençol de Elástico Infantil - Vila Das Fadas", "handle": "lencol-de-elastico-infantil-vila-das-fadas"}}},
        ]},
    }
    client = SequenceClient([{"data": {"productVariant": variant}}])
    result = await ShopifyOperations(client).get_product_variant({"id": "gid://shopify/ProductVariant/1"})
    assert "productVariantComponents" in client.calls[0][0]
    assert result["variant"]["requiresComponents"] is True
    skus = [node["productVariant"]["sku"] for node in result["variant"]["productVariantComponents"]["nodes"]]
    assert skus == ["14771", "14757"]


@pytest.mark.asyncio
async def test_get_product_query_requests_components():
    client = SequenceClient([{"data": {"product": {"id": "gid://shopify/Product/1", "variants": {"nodes": []}}}}])
    await ShopifyOperations(client).get_product({"id": "gid://shopify/Product/1"})
    assert "productVariantComponents" in client.calls[0][0]
    assert "requiresComponents" in client.calls[0][0]


@pytest.mark.asyncio
async def test_get_product_variant_by_sku_requests_components():
    client = SequenceClient([{"data": {"productVariants": {"nodes": []}}}])
    await ShopifyOperations(client).get_product_variant_by_sku({"sku": "14771"})
    assert "productVariantComponents" in client.calls[0][0]


@pytest.mark.asyncio
async def test_list_endpoints_flag_bundles():
    for op, key in (("list_products", "products"), ("list_product_variants", "productVariants")):
        response = {"data": {key: {"edges": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}
        client = SequenceClient([response])
        await getattr(ShopifyOperations(client), op)({"first": 5})
        assert "requiresComponents" in client.calls[0][0]


@pytest.mark.asyncio
async def test_shopifyql_query_passes_query_and_returns_table():
    table = {"__typename": "TableResponse", "parseErrors": [],
             "tableData": {"columns": [{"name": "bundle_title", "dataType": "string", "displayName": "Bundle"}],
                           "rowData": [["Jogo de Cama Berço Duo", "14771"]]}}
    client = SequenceClient([{"data": {"shopifyqlQuery": table}}])
    result = await ShopifyOperations(client).shopifyql_query({"query": "FROM sales SHOW bundles_ordered WHERE line_item_is_bundle = true"})
    assert client.calls[0][1] == {"q": "FROM sales SHOW bundles_ordered WHERE line_item_is_bundle = true"}
    assert "shopifyqlQuery" in client.calls[0][0]
    assert result["shopifyql"]["tableData"]["rowData"][0][1] == "14771"
