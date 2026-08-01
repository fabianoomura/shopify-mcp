import pytest

from shopify_mcp.client import ShopifyClient, ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


@pytest.mark.asyncio
async def test_write_requires_feature_flag():
    ops = ShopifyOperations(ShopifyClient(Settings("test.myshopify.com", "secret", enable_writes=False)))
    with pytest.raises(ShopifyError, match="desabilitadas"):
        await ops.add_tags({"id": "gid://shopify/Product/1", "tags": ["x"], "confirmationToken": "unused"})
    await ops.client.close()


@pytest.mark.asyncio
async def test_write_requires_confirmation():
    ops = ShopifyOperations(ShopifyClient(Settings("test.myshopify.com", "secret", enable_writes=True)))
    with pytest.raises(ShopifyError, match="confirmationToken"):
        await ops.remove_tags({"id": "gid://shopify/Product/1", "tags": ["x"]})
    await ops.client.close()
