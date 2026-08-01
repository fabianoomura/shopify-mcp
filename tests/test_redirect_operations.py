import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.confirmations import ConfirmationError
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    async def graphql(self, query, variables=None):
        self.calls.append((query, variables)); return self.responses.pop(0)


def test_redirect_rejects_direct_loop():
    with pytest.raises(ValueError, match="próprio caminho"):
        ShopifyOperations._validate_redirect("/antigo/", "/antigo")


@pytest.mark.asyncio
async def test_redirect_create_rejects_existing_path():
    existing = {"id": "gid://shopify/UrlRedirect/1", "path": "/a", "target": "/b"}
    client = SequenceClient([{"data": {"urlRedirects": {"nodes": [existing]}}}])
    with pytest.raises(ShopifyError, match="Já existe"):
        await ShopifyOperations(client).prepare_url_redirect_create({"path": "/a", "target": "/c"})


@pytest.mark.asyncio
async def test_redirect_token_binds_target():
    client = SequenceClient([{"data": {"urlRedirects": {"nodes": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_url_redirect_create({"path": "/a", "target": "/b"})
    with pytest.raises(ConfirmationError):
        await ops.create_url_redirect({"path": "/a", "target": "/c", "confirmationToken": proposal["confirmationToken"]})


@pytest.mark.asyncio
async def test_redirect_delete_uses_official_payload_field():
    redirect = {"id": "gid://shopify/UrlRedirect/1", "path": "/a", "target": "/b"}
    client = SequenceClient([{"data": {"urlRedirect": redirect}}, {"data": {"urlRedirectDelete": {"deletedUrlRedirectId": redirect["id"], "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_url_redirect_delete({"id": redirect["id"]})
    result = await ops.delete_url_redirect({"id": redirect["id"], "confirmationToken": proposal["confirmationToken"]})
    assert result["deletedUrlRedirectId"] == redirect["id"]
