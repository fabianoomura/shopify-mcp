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


def menu_items(target="/collections/all"):
    return [{"title": "Catálogo", "type": "CATALOG", "url": target, "items": []}]


def test_menu_resource_type_must_match_gid():
    items = [{"title": "X", "type": "PRODUCT", "url": "/products/x", "resourceId": "gid://shopify/Collection/1", "items": []}]
    with pytest.raises(ValueError, match="incompatível"):
        ShopifyOperations._menu_resource_ids(items)


@pytest.mark.asyncio
async def test_menu_create_token_binds_complete_tree():
    client = SequenceClient([{"data": {"menus": {"nodes": []}}}])
    ops = ShopifyOperations(client)
    request = {"title": "Principal", "handle": "principal", "items": menu_items()}
    proposal = await ops.prepare_menu_create(request)
    with pytest.raises(ConfirmationError):
        await ops.create_menu({**request, "items": menu_items("/search"), "confirmationToken": proposal["confirmationToken"]})


@pytest.mark.asyncio
async def test_menu_update_protects_default_handle():
    current = {"id": "gid://shopify/Menu/1", "title": "Main", "handle": "main-menu", "isDefault": True, "items": []}
    client = SequenceClient([{"data": {"menu": current}}])
    with pytest.raises(ShopifyError, match="padrão"):
        await ShopifyOperations(client).prepare_menu_update({"id": current["id"], "title": "Main", "handle": "novo", "items": []})


@pytest.mark.asyncio
async def test_menu_delete_rejects_default_before_token():
    menu = {"id": "gid://shopify/Menu/1", "title": "Main", "handle": "main-menu", "isDefault": True, "items": []}
    with pytest.raises(ShopifyError, match="padrão"):
        await ShopifyOperations(SequenceClient([{"data": {"menu": menu}}])).prepare_menu_delete({"id": menu["id"]})
