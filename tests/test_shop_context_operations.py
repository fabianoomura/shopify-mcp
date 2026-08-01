import pytest

from shopify_mcp.operations import ShopifyOperations


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.payload


@pytest.mark.asyncio
async def test_access_scopes_are_sorted_and_counted():
    client = FakeClient({"data": {"currentAppInstallation": {
        "id": "gid://shopify/AppInstallation/1",
        "accessScopes": [
            {"handle": "write_products", "description": "Write"},
            {"handle": "read_products", "description": "Read"},
        ],
    }}})
    result = await ShopifyOperations(client).get_access_scopes({})
    assert result["count"] == 2
    assert [scope["handle"] for scope in result["scopes"]] == ["read_products", "write_products"]


@pytest.mark.asyncio
async def test_publications_are_flattened_with_cursor():
    client = FakeClient({"data": {"publications": {
        "edges": [{"cursor": "cursor-1", "node": {"id": "gid://shopify/Publication/1", "name": "Online Store"}}],
        "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
    }}})
    result = await ShopifyOperations(client).list_publications({"first": 10})
    assert result["items"][0]["name"] == "Online Store"
    assert result["pageInfo"]["endCursor"] == "cursor-1"
    assert client.calls[0][1] == {"first": 10, "after": None}


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "key"), [
    ("list_product_types", "productTypes"),
    ("list_product_vendors", "productVendors"),
])
async def test_string_connections(method, key):
    client = FakeClient({"data": {key: {
        "edges": [{"cursor": "c", "node": "MOOUI"}],
        "pageInfo": {"hasNextPage": False, "endCursor": "c"},
    }}})
    result = await getattr(ShopifyOperations(client), method)({})
    assert result["items"] == ["MOOUI"]
