import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.confirmations import ConfirmationError
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
async def test_page_create_checks_handle_and_binds_html():
    client = SequenceClient([{"data": {"pages": {"nodes": []}}}, {"data": {"pageCreate": {"page": {"id": "gid://shopify/Page/1"}, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    request = {"title": "Sobre", "handle": "sobre", "body": "<p>MOOUI</p>", "isPublished": False}
    proposal = await ops.prepare_page_create(request)
    result = await ops.create_page({**request, "confirmationToken": proposal["confirmationToken"]})
    assert client.calls[-1][1]["page"]["body"] == "<p>MOOUI</p>"
    assert result["operation"] == "pageCreate"


@pytest.mark.asyncio
async def test_page_create_rejects_duplicate_handle():
    response = {"data": {"pages": {"nodes": [{"id": "gid://shopify/Page/1", "title": "Sobre", "handle": "sobre", "isPublished": True}]}}}
    with pytest.raises(ShopifyError, match="já existe"):
        await ShopifyOperations(SequenceClient([response])).prepare_page_create({"title": "Outra", "handle": "sobre", "isPublished": False})


@pytest.mark.asyncio
async def test_page_update_token_binds_publish_status():
    current = {"data": {"page": {"id": "gid://shopify/Page/1", "title": "Sobre", "handle": "sobre", "body": "x", "isPublished": False, "publishedAt": None, "templateSuffix": None}}}
    ops = ShopifyOperations(SequenceClient([current]))
    proposal = await ops.prepare_page_update({"id": "gid://shopify/Page/1", "isPublished": True})
    with pytest.raises(ConfirmationError):
        await ops.update_page({"id": "gid://shopify/Page/1", "isPublished": False, "confirmationToken": proposal["confirmationToken"]})


def test_page_rejects_hidden_scheduled_state():
    with pytest.raises(ValueError, match="publishDate"):
        ShopifyOperations._validate_page_input({"isPublished": False, "publishDate": "2026-09-01T00:00:00Z"})


@pytest.mark.asyncio
async def test_page_delete_is_one_use():
    page = {"id": "gid://shopify/Page/1", "title": "Antiga", "handle": "antiga", "bodySummary": "", "isPublished": False, "publishedAt": None, "updatedAt": "2026-01-01T00:00:00Z"}
    client = SequenceClient([{"data": {"page": page}}, {"data": {"pageDelete": {"deletedPageId": page["id"], "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_page_delete({"id": page["id"]})
    apply = {"id": page["id"], "confirmationToken": proposal["confirmationToken"]}
    assert (await ops.delete_page(apply))["deletedPageId"] == page["id"]
    with pytest.raises(ConfirmationError):
        await ops.delete_page(apply)
