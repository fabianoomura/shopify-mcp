import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    async def graphql(self, query, variables=None): self.calls.append((query, variables)); return self.responses.pop(0)


def preview(*, supports=True, published=False, status="ACTIVE"):
    return {"data": {"node": {"id": "gid://shopify/Product/1", "__typename": "Product", "title": "P", "status": status, "requiresSellingPlan": False, "publication0": published}, "nodes": [{"id": "gid://shopify/Publication/2", "name": "Online Store", "supportsFuturePublishing": supports, "autoPublish": False}]}}


@pytest.mark.asyncio
async def test_publish_rejects_schedule_on_unsupported_channel():
    args = {"id": "gid://shopify/Product/1", "publications": [{"publicationId": "gid://shopify/Publication/2", "publishDate": "2999-01-01T00:00:00Z"}]}
    with pytest.raises(ShopifyError, match="não suporta"):
        await ShopifyOperations(SequenceClient([preview(supports=False)])).prepare_publish(args)


@pytest.mark.asyncio
async def test_inactive_product_is_explicitly_warned_and_published():
    payload = {"data": {"publishablePublish": {"publishable": {"availablePublicationsCount": {"count": 1}}, "userErrors": []}}}
    client = SequenceClient([preview(status="DRAFT"), payload]); ops = ShopifyOperations(client)
    request = {"id": "gid://shopify/Product/1", "publications": [{"publicationId": "gid://shopify/Publication/2"}]}
    proposal = await ops.prepare_publish(request)
    assert "ACTIVE" in proposal["warnings"][0]
    result = await ops.publish({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["operation"] == "publishablePublish"


@pytest.mark.asyncio
async def test_unpublish_maps_ids_to_official_publication_input():
    payload = {"data": {"publishableUnpublish": {"publishable": {"availablePublicationsCount": {"count": 0}}, "userErrors": []}}}
    client = SequenceClient([preview(published=True), payload]); ops = ShopifyOperations(client)
    request = {"id": "gid://shopify/Product/1", "publicationIds": ["gid://shopify/Publication/2"]}
    proposal = await ops.prepare_unpublish(request)
    await ops.unpublish({**request, "confirmationToken": proposal["confirmationToken"]})
    assert client.calls[-1][1]["input"] == [{"publicationId": "gid://shopify/Publication/2"}]
