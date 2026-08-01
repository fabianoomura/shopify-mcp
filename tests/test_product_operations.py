import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.operations import ShopifyOperations
from shopify_mcp.config import Settings


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.variables = None

    async def graphql(self, _query, variables=None):
        self.variables = variables
        return {"data": self.data}


@pytest.mark.asyncio
async def test_product_by_handle_uses_identifier_input():
    client = FakeClient({"productByIdentifier": {"id": "gid://shopify/Product/1", "handle": "winter-sheet"}})
    result = await ShopifyOperations(client).get_product_by_handle({"handle": "winter-sheet"})
    assert result["product"]["id"].endswith("/1")
    assert client.variables == {"identifier": {"handle": "winter-sheet"}}


@pytest.mark.asyncio
async def test_variant_by_sku_escapes_search_and_returns_unique_match():
    client = FakeClient({"productVariants": {"nodes": [{"id": "gid://shopify/ProductVariant/1", "sku": 'A"B'}]}})
    result = await ShopifyOperations(client).get_product_variant_by_sku({"sku": 'A"B'})
    assert result["variant"]["sku"] == 'A"B'
    assert client.variables == {"query": 'sku:"A\\"B"'}


@pytest.mark.asyncio
async def test_variant_by_sku_rejects_ambiguous_sku():
    client = FakeClient({"productVariants": {"nodes": [{"id": "1"}, {"id": "2"}]}})
    with pytest.raises(ShopifyError, match="ambíguo"):
        await ShopifyOperations(client).get_product_variant_by_sku({"sku": "DUPLICATE"})


@pytest.mark.asyncio
async def test_product_count_preserves_precision():
    client = FakeClient({"productsCount": {"count": 25001, "precision": "AT_LEAST"}})
    result = await ShopifyOperations(client).count_products({"query": "status:active"})
    assert result == {"productsCount": {"count": 25001, "precision": "AT_LEAST"}}


@pytest.mark.asyncio
async def test_seo_prepare_and_apply_with_single_use_token():
    class SequenceClient:
        settings = Settings("test.myshopify.com", "secret", enable_writes=True)

        def __init__(self):
            self.responses = [
                {"data": {"product": {"id": "gid://shopify/Product/1", "title": "Sheet", "handle": "sheet", "seo": {"title": "Old", "description": "Old desc"}}}},
                {"data": {"productUpdate": {"product": {"id": "gid://shopify/Product/1", "seo": {"title": "New", "description": "Old desc"}}, "userErrors": []}}},
            ]

        async def graphql(self, _query, _variables=None):
            return self.responses.pop(0)

    ops = ShopifyOperations(SequenceClient())
    preview = await ops.prepare_product_seo_update({"id": "gid://shopify/Product/1", "title": "New"})
    assert preview["before"]["title"] == "Old"
    assert preview["after"]["title"] == "New"
    apply_args = {"id": "gid://shopify/Product/1", "title": "New", "confirmationToken": preview["confirmationToken"]}
    result = await ops.update_product_seo(apply_args)
    assert result["success"] is True
    with pytest.raises(ValueError, match="já utilizado"):
        await ops.update_product_seo(apply_args)


@pytest.mark.asyncio
async def test_product_create_prepare_apply_keeps_unpublished_workflow():
    class CreateClient:
        settings = Settings("test.myshopify.com", "secret", enable_writes=True)

        async def graphql(self, _query, variables=None):
            assert variables["product"]["title"] == "New Sheet"
            assert "confirmationToken" not in variables["product"]
            return {"data": {"productCreate": {"product": {"id": "gid://shopify/Product/2", "title": "New Sheet", "status": "DRAFT"}, "userErrors": []}}}

    ops = ShopifyOperations(CreateClient())
    prepared = await ops.prepare_product_create({"title": "New Sheet", "status": "DRAFT", "vendor": "MOOUI"})
    assert prepared["before"] is None
    assert "sem publicação" in prepared["warnings"][0]
    result = await ops.create_product({"title": "New Sheet", "status": "DRAFT", "vendor": "MOOUI", "confirmationToken": prepared["confirmationToken"]})
    assert result["product"]["id"].endswith("/2")


@pytest.mark.asyncio
async def test_product_update_prepare_apply_is_bound_to_changes():
    class UpdateClient:
        settings = Settings("test.myshopify.com", "secret", enable_writes=True)

        def __init__(self):
            self.responses = [
                {"data": {"product": {"id": "gid://shopify/Product/1", "title": "Old", "descriptionHtml": "", "handle": "old", "vendor": "MOOUI", "productType": "Sheet", "status": "DRAFT", "category": None, "tags": [], "seo": {}, "templateSuffix": None, "requiresSellingPlan": False}}},
                {"data": {"productUpdate": {"product": {"id": "gid://shopify/Product/1", "title": "New"}, "userErrors": []}}},
            ]

        async def graphql(self, _query, _variables=None):
            return self.responses.pop(0)

    ops = ShopifyOperations(UpdateClient())
    prepared = await ops.prepare_product_update({"id": "gid://shopify/Product/1", "title": "New"})
    assert prepared["before"]["title"] == "Old"
    assert prepared["after"]["title"] == "New"
    with pytest.raises(ValueError, match="corresponde"):
        await ops.update_product({"id": "gid://shopify/Product/1", "title": "Different", "confirmationToken": prepared["confirmationToken"]})
