import pytest

from shopify_mcp.catalog import enabled_definitions
from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.confirmations import ConfirmationError
from shopify_mcp.operations import ShopifyOperations


class Client:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


def bxgy_request():
    return {
        "title": "3x2 Pillowcases", "startsAt": "2026-10-21T00:00:00Z",
        "buysQuantity": 2, "buysTargetType": "COLLECTIONS", "buysCollectionIds": ["gid://shopify/Collection/1"],
        "getsQuantity": 1, "getsPercentage": 1, "getsTargetType": "COLLECTIONS", "getsCollectionIds": ["gid://shopify/Collection/1"],
        "combinesWith": {"orderDiscounts": False, "productDiscounts": True, "shippingDiscounts": True},
    }


def preview(nodes=None, existing=None):
    nodes = nodes if nodes is not None else [{"__typename": "Collection", "id": "gid://shopify/Collection/1", "title": "Pillowcases", "productsCount": {"count": 40}}]
    return {"data": {"nodes": nodes, "automaticDiscountNodes": {"nodes": existing or []}}}


@pytest.mark.asyncio
async def test_bxgy_builds_three_for_two_input_and_creates_with_token():
    created = {"data": {"discountAutomaticBxgyCreate": {"automaticDiscountNode": {"id": "gid://shopify/DiscountAutomaticNode/9"}, "userErrors": []}}}
    client = Client(preview(), created)
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_discount_automatic_bxgy_create(bxgy_request())
    shopify_input = proposal["shopifyInput"]
    assert shopify_input["customerBuys"] == {"value": {"quantity": "2"}, "items": {"collections": {"add": ["gid://shopify/Collection/1"]}}}
    assert shopify_input["customerGets"]["value"] == {"discountOnQuantity": {"quantity": "1", "effect": {"percentage": 1}}}
    assert "usesPerOrderLimit" not in shopify_input
    assert client.calls[0][1]["ids"] == ["gid://shopify/Collection/1"]
    result = await ops.create_discount_automatic_bxgy({**bxgy_request(), "confirmationToken": proposal["confirmationToken"]})
    assert result["automaticDiscountNode"]["id"].endswith("/9")
    assert "discountAutomaticBxgyCreate(automaticBxgyDiscount:$automaticBxgyDiscount)" in client.calls[1][0]


@pytest.mark.asyncio
async def test_bxgy_token_rejects_changed_quantity():
    ops = ShopifyOperations(Client(preview()))
    proposal = await ops.prepare_discount_automatic_bxgy_create(bxgy_request())
    with pytest.raises(ConfirmationError):
        await ops.create_discount_automatic_bxgy({**bxgy_request(), "buysQuantity": 1, "confirmationToken": proposal["confirmationToken"]})


@pytest.mark.asyncio
async def test_bxgy_rejects_missing_targets():
    with pytest.raises(ShopifyError, match="não encontrados"):
        await ShopifyOperations(Client(preview(nodes=[None]))).prepare_discount_automatic_bxgy_create(bxgy_request())


@pytest.mark.asyncio
async def test_bxgy_warns_on_same_title_and_no_product_combination():
    existing = [{"id": "gid://shopify/DiscountAutomaticNode/5", "automaticDiscount": {"__typename": "DiscountAutomaticBxgy", "title": "3x2 Pillowcases", "status": "EXPIRED"}}]
    request = {**bxgy_request(), "combinesWith": {"orderDiscounts": False, "productDiscounts": False, "shippingDiscounts": False}}
    proposal = await ShopifyOperations(Client(preview(existing=existing))).prepare_discount_automatic_bxgy_create(request)
    joined = " ".join(proposal["warnings"])
    assert "DiscountAutomaticNode/5" in joined
    assert "productDiscounts=false" in joined


def test_bxgy_shape_validation():
    with pytest.raises(ValueError, match="exatamente um"):
        ShopifyOperations._validate_automatic_bxgy_shape({**bxgy_request(), "buysMinimumAmount": "50.00"})
    with pytest.raises(ValueError, match="incompatíveis"):
        ShopifyOperations._validate_automatic_bxgy_shape({**bxgy_request(), "buysProductIds": ["gid://shopify/Product/1"]})
    with pytest.raises(ValueError, match="exige getsProductIds"):
        ShopifyOperations._validate_automatic_bxgy_shape({**bxgy_request(), "getsTargetType": "PRODUCTS"})
    with pytest.raises(ValueError, match="endsAt"):
        ShopifyOperations._validate_automatic_bxgy_shape({**bxgy_request(), "endsAt": "2026-10-01T00:00:00Z"})


def test_bxgy_input_keeps_uses_per_order_limit_and_amount():
    request = {**bxgy_request(), "usesPerOrderLimit": 1}
    del request["buysQuantity"]
    request["buysMinimumAmount"] = "100.00"
    value = ShopifyOperations._automatic_bxgy_input(request)
    assert value["usesPerOrderLimit"] == "1"
    assert value["customerBuys"]["value"] == {"amount": "100.00"}


@pytest.mark.asyncio
async def test_automatic_status_token_binds_action():
    node = {"id": "gid://shopify/DiscountAutomaticNode/1", "automaticDiscount": {"__typename": "DiscountAutomaticBxgy", "title": "3x2", "status": "ACTIVE"}}
    ops = ShopifyOperations(Client({"data": {"automaticDiscountNode": node}}))
    proposal = await ops.prepare_discount_automatic_status_change({"id": node["id"], "action": "DEACTIVATE"})
    assert proposal["willChange"] is True
    with pytest.raises(ConfirmationError):
        await ops.set_discount_automatic_status({"id": node["id"], "action": "ACTIVATE", "confirmationToken": proposal["confirmationToken"]})


@pytest.mark.asyncio
async def test_automatic_delete_returns_deleted_id():
    node = {"id": "gid://shopify/DiscountAutomaticNode/1", "automaticDiscount": {"__typename": "DiscountAutomaticBxgy", "title": "3x2", "status": "EXPIRED"}}
    deleted = {"data": {"discountAutomaticDelete": {"deletedAutomaticDiscountId": node["id"], "userErrors": []}}}
    ops = ShopifyOperations(Client({"data": {"automaticDiscountNode": node}}, deleted))
    proposal = await ops.prepare_discount_automatic_delete({"id": node["id"]})
    result = await ops.delete_discount_automatic({"id": node["id"], "confirmationToken": proposal["confirmationToken"]})
    assert result["deletedAutomaticDiscountId"] == node["id"]


@pytest.mark.asyncio
async def test_list_automatic_discounts_uses_connection():
    response = {"data": {"automaticDiscountNodes": {"edges": [{"cursor": "c", "node": {"id": "gid://shopify/DiscountAutomaticNode/1"}}], "pageInfo": {"hasNextPage": False, "endCursor": "c"}}}}
    client = Client(response)
    result = await ShopifyOperations(client).list_automatic_discounts({"query": "status:active"})
    assert result["items"][0]["id"].endswith("/1")
    assert "DiscountAutomaticBxgy" in client.calls[0][0]


def test_automatic_discount_writes_available_in_catalog_but_not_code_discounts():
    names = {item.tool.name for item in enabled_definitions("catalog", True)}
    assert "shopify_create_discount_automatic_bxgy" in names
    assert "shopify_create_discount_code_basic" not in names
