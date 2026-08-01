import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.confirmations import ConfirmationError
from shopify_mcp.operations import ShopifyOperations


class Client:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)

    def __init__(self, response):
        self.response = response
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.response


@pytest.mark.asyncio
async def test_discount_lookup_by_code_is_case_insensitive_server_operation():
    node = {"id": "gid://shopify/DiscountCodeNode/1", "codeDiscount": {"__typename": "DiscountCodeBasic", "title": "VIP"}}
    client = Client({"data": {"codeDiscountNodeByCode": node}})
    result = await ShopifyOperations(client).get_code_discount_by_code({"code": "vip10"})
    query, variables = client.calls[0]
    assert "codeDiscountNodeByCode(code:$code)" in query
    assert "DiscountCodeFreeShipping" in query
    assert variables == {"code": "vip10"}
    assert result["codeDiscountNode"] == node


@pytest.mark.asyncio
async def test_discount_list_preserves_cursor_page_info():
    response = {"data": {"codeDiscountNodes": {"edges": [{"cursor": "c1", "node": {"id": "gid://shopify/DiscountCodeNode/1"}}], "pageInfo": {"hasNextPage": True, "endCursor": "c1"}}}}
    result = await ShopifyOperations(Client(response)).list_code_discounts({"first": 10, "query": "status:active"})
    assert result["items"][0]["id"].endswith("/1")
    assert result["pageInfo"]["endCursor"] == "c1"


def basic_request():
    return {
        "title": "VIP 10%", "code": "VIP10", "startsAt": "2026-08-01T00:00:00Z",
        "endsAt": "2026-09-01T00:00:00Z", "valueType": "PERCENTAGE", "percentage": 0.1,
        "targetType": "PRODUCTS", "productIds": ["gid://shopify/Product/2"],
        "audienceType": "ALL", "minimumType": "SUBTOTAL", "minimumSubtotal": "100.00",
        "usageLimit": 100, "appliesOncePerCustomer": True,
        "combinesWith": {"orderDiscounts": False, "productDiscounts": False, "shippingDiscounts": True},
    }


@pytest.mark.asyncio
async def test_basic_discount_resolves_ids_and_binds_transformed_input():
    preview = {"data": {"codeDiscountNodeByCode": None, "nodes": [{"id": "gid://shopify/Product/2", "__typename": "Product", "title": "P", "status": "ACTIVE"}]}}
    created = {"data": {"discountCodeBasicCreate": {"codeDiscountNode": {"id": "gid://shopify/DiscountCodeNode/3"}, "userErrors": []}}}
    client = Client(preview)
    client.responses = [preview, created]
    async def graphql(query, variables=None):
        client.calls.append((query, variables))
        return client.responses.pop(0)
    client.graphql = graphql
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_discount_code_basic_create(basic_request())
    assert proposal["shopifyInput"]["context"] == {"all": "ALL"}
    assert proposal["shopifyInput"]["customerGets"]["items"] == {"products": {"productsToAdd": ["gid://shopify/Product/2"]}}
    result = await ops.create_discount_code_basic({**basic_request(), "confirmationToken": proposal["confirmationToken"]})
    assert result["operation"] == "discountCodeBasicCreate"


@pytest.mark.asyncio
async def test_basic_discount_rejects_existing_code():
    existing = {"data": {"codeDiscountNodeByCode": {"id": "gid://shopify/DiscountCodeNode/9"}, "nodes": []}}
    with pytest.raises(ShopifyError, match="já existe"):
        await ShopifyOperations(Client(existing)).prepare_discount_code_basic_create({**basic_request(), "targetType": "ALL", "productIds": []})


@pytest.mark.asyncio
async def test_basic_discount_rejects_changed_percentage_after_preview():
    preview = {"data": {"codeDiscountNodeByCode": None, "nodes": [{"id": "gid://shopify/Product/2", "__typename": "Product", "title": "P", "status": "ACTIVE"}]}}
    ops = ShopifyOperations(Client(preview))
    proposal = await ops.prepare_discount_code_basic_create(basic_request())
    with pytest.raises(ConfirmationError):
        await ops.create_discount_code_basic({**basic_request(), "percentage": 0.2, "confirmationToken": proposal["confirmationToken"]})


def test_basic_discount_rejects_incompatible_value_fields():
    with pytest.raises(ValueError, match="incompatíveis"):
        ShopifyOperations._validate_discount_basic_shape({**basic_request(), "fixedAmount": "10.00"})


@pytest.mark.asyncio
async def test_discount_status_token_binds_action():
    node = {"id": "gid://shopify/DiscountCodeNode/1", "codeDiscount": {"__typename": "DiscountCodeBasic", "title": "VIP", "status": "ACTIVE"}}
    ops = ShopifyOperations(Client({"data": {"codeDiscountNode": node}}))
    proposal = await ops.prepare_discount_code_status_change({"id": node["id"], "action": "DEACTIVATE"})
    with pytest.raises(ConfirmationError):
        await ops.set_discount_code_status({"id": node["id"], "action": "ACTIVATE", "confirmationToken": proposal["confirmationToken"]})


@pytest.mark.asyncio
async def test_discount_delete_returns_official_deleted_id():
    node = {"id": "gid://shopify/DiscountCodeNode/1", "codeDiscount": {"__typename": "DiscountCodeBasic", "title": "VIP", "status": "EXPIRED"}}
    preview = {"data": {"codeDiscountNode": node}}
    deleted = {"data": {"discountCodeDelete": {"deletedCodeDiscountId": node["id"], "userErrors": []}}}
    client = Client(preview)
    client.responses = [preview, deleted]
    async def graphql(query, variables=None):
        client.calls.append((query, variables))
        return client.responses.pop(0)
    client.graphql = graphql
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_discount_code_delete({"id": node["id"]})
    result = await ops.delete_discount_code({"id": node["id"], "confirmationToken": proposal["confirmationToken"]})
    assert result["deletedCodeDiscountId"] == node["id"]
