import pytest

from shopify_mcp.catalog import BY_NAME
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


COLLECTION = {"id": "gid://shopify/Collection/1", "title": "Verão", "descriptionHtml": "", "handle": "verao", "sortOrder": "MANUAL", "templateSuffix": None, "seo": {"title": "Verão", "description": ""}, "productsCount": {"count": 2}, "sources": []}


@pytest.mark.asyncio
async def test_collection_create_is_modern_and_unpublished():
    client = SequenceClient([{"data": {"collectionCreate": {"collection": COLLECTION, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    payload = {"title": "Verão", "sortOrder": "MANUAL"}
    proposal = await ops.prepare_collection_create(payload)
    assert "sem publicação" in proposal["warnings"][0]
    result = await ops.create_collection({**payload, "confirmationToken": proposal["confirmationToken"]})
    query, variables = client.calls[-1]
    assert "CollectionCreateInput!" in query
    assert "collectionCreate(collection:$collection)" in query
    assert variables == {"collection": payload}
    assert result["operation"] == "collectionCreate"


@pytest.mark.asyncio
async def test_collection_delete_preview_is_irreversible_and_tool_is_destructive():
    client = SequenceClient([
        {"data": {"collection": {**COLLECTION, "publications": {"nodes": [{"id": "gid://shopify/Publication/1", "name": "Online Store"}]}}}},
        {"data": {"collectionDelete": {"deletedCollectionId": COLLECTION["id"], "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_collection_delete({"id": COLLECTION["id"]})
    assert proposal["irreversible"] is True
    result = await ops.delete_collection({"id": COLLECTION["id"], "confirmationToken": proposal["confirmationToken"]})
    assert result["deletedCollectionId"] == COLLECTION["id"]
    assert BY_NAME["shopify_delete_collection"].tool.annotations.destructiveHint is True


@pytest.mark.asyncio
async def test_product_membership_rejects_same_collection_join_and_leave_without_api_call():
    client = SequenceClient([])
    payload = {"id": "gid://shopify/Product/1", "collectionsToJoin": [COLLECTION["id"]], "collectionsToLeave": [COLLECTION["id"]]}
    with pytest.raises(ValueError, match="mesma coleção"):
        await ShopifyOperations(client).prepare_product_update(payload)
    assert client.calls == []
