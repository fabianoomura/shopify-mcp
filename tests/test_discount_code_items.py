import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.confirmations import ConfirmationError
from shopify_mcp.operations import ShopifyOperations

CODE = "gid://shopify/DiscountCodeNode/1"
OLD = "gid://shopify/Collection/10"
NEW = "gid://shopify/Collection/20"


class Client:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


def state(items=None, typename="DiscountCodeBasic", targets=None):
    items = items if items is not None else {"collections": {"nodes": [{"id": OLD, "title": "produtos fora da sale"}]}}
    discount = {"__typename": typename, "title": "MYFIRSTMOOUI", "summary": "10% off", "customerGets": {"items": items}}
    targets = targets if targets is not None else [{"__typename": "Collection", "id": NEW, "title": "sem 3x2", "productsCount": {"count": 532}}]
    return {"data": {"codeDiscountNode": {"id": CODE, "codeDiscount": discount}, "nodes": targets}}


@pytest.mark.asyncio
async def test_items_swap_collection_removes_old_and_adds_new():
    updated = {"data": {"discountCodeBasicUpdate": {"codeDiscountNode": {"id": CODE}, "userErrors": []}}}
    client = Client(state(), state(), updated)
    ops = ShopifyOperations(client)
    request = {"id": CODE, "targetType": "COLLECTIONS", "collectionIds": [NEW]}
    proposal = await ops.prepare_discount_code_items_update(request)
    assert proposal["shopifyInput"] == {"customerGets": {"items": {"collections": {"add": [NEW], "remove": [OLD]}}}}
    assert proposal["before"]["collections"]["nodes"][0]["id"] == OLD
    result = await ops.update_discount_code_items({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["operation"] == "discountCodeBasicUpdate"
    assert client.calls[2][1] == {"id": CODE, "basicCodeDiscount": {"customerGets": {"items": {"collections": {"add": [NEW], "remove": [OLD]}}}}}


@pytest.mark.asyncio
async def test_items_token_rejects_target_changed_since_preview():
    changed = state(items={"collections": {"nodes": [{"id": "gid://shopify/Collection/99", "title": "outra"}]}})
    ops = ShopifyOperations(Client(state(), changed))
    request = {"id": CODE, "targetType": "COLLECTIONS", "collectionIds": [NEW]}
    proposal = await ops.prepare_discount_code_items_update(request)
    with pytest.raises(ConfirmationError):
        await ops.update_discount_code_items({**request, "confirmationToken": proposal["confirmationToken"]})


@pytest.mark.asyncio
async def test_items_rejects_non_basic_and_missing_targets():
    with pytest.raises(ShopifyError, match="DiscountCodeBasic"):
        await ShopifyOperations(Client(state(typename="DiscountCodeBxgy"))).prepare_discount_code_items_update({"id": CODE, "targetType": "COLLECTIONS", "collectionIds": [NEW]})
    with pytest.raises(ShopifyError, match="não encontrados"):
        await ShopifyOperations(Client(state(targets=[None]))).prepare_discount_code_items_update({"id": CODE, "targetType": "COLLECTIONS", "collectionIds": [NEW]})


@pytest.mark.asyncio
async def test_items_shape_validation():
    ops = ShopifyOperations(Client())
    with pytest.raises(ValueError, match="exige collectionIds"):
        await ops.prepare_discount_code_items_update({"id": CODE, "targetType": "COLLECTIONS"})
    with pytest.raises(ValueError, match="incompatíveis"):
        await ops.prepare_discount_code_items_update({"id": CODE, "targetType": "ALL", "collectionIds": [NEW]})


def test_items_refuses_when_current_targets_may_be_truncated():
    current = {"collections": {"nodes": [{"id": f"gid://shopify/Collection/{n}"} for n in range(20)]}}
    with pytest.raises(ShopifyError, match="20"):
        ShopifyOperations._discount_items_diff(current, {"targetType": "COLLECTIONS", "collectionIds": [NEW]})
