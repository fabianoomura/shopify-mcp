import pytest

from shopify_mcp.operations import ShopifyOperations


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.variables = None

    async def graphql(self, _query, variables=None):
        self.variables = variables
        return {"data": self.data}


@pytest.mark.asyncio
async def test_collection_by_handle_uses_identifier():
    client = FakeClient({"collectionByIdentifier": {"id": "gid://shopify/Collection/1", "handle": "winter"}})
    result = await ShopifyOperations(client).get_collection_by_handle({"handle": "winter"})
    assert result["collection"]["handle"] == "winter"
    assert client.variables == {"identifier": {"handle": "winter"}}


@pytest.mark.asyncio
@pytest.mark.parametrize(("rule_set", "automated"), [(None, False), ({"appliedDisjunctively": False}, True)])
async def test_collection_products_identifies_automated_collection(rule_set, automated):
    client = FakeClient({"collection": {
        "id": "gid://shopify/Collection/1", "title": "Winter", "handle": "winter", "ruleSet": rule_set,
        "products": {"edges": [{"cursor": "c", "node": {"id": "gid://shopify/Product/1"}}], "pageInfo": {"hasNextPage": False, "endCursor": "c"}},
    }})
    result = await ShopifyOperations(client).list_collection_products({"id": "gid://shopify/Collection/1"})
    assert result["collection"]["automated"] is automated
    assert result["items"][0]["id"].endswith("/1")


@pytest.mark.asyncio
async def test_missing_collection_has_empty_safe_result():
    result = await ShopifyOperations(FakeClient({"collection": None})).list_collection_products({"id": "gid://shopify/Collection/1"})
    assert result == {"collection": None, "items": [], "pageInfo": {}}
