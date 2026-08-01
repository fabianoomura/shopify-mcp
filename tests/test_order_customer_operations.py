import pytest

from shopify_mcp.catalog import BY_NAME
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
async def test_customer_detail_separates_paginated_orders_and_marks_pii():
    customer = {"id": "gid://shopify/Customer/1", "displayName": "Cliente", "email": "c@example.com", "orders": {"edges": [{"cursor": "c1", "node": {"id": "gid://shopify/Order/1"}}], "pageInfo": {"hasNextPage": False, "endCursor": "c1"}}}
    result = await ShopifyOperations(SequenceClient([{"data": {"customer": customer}}])).get_customer({"id": customer["id"], "first": 10})
    assert result["containsPII"] is True
    assert result["orders"] == [{"id": "gid://shopify/Order/1"}]
    assert "orders" not in result["customer"]


@pytest.mark.asyncio
async def test_order_update_warns_for_overwrite_and_binds_exact_list():
    before = {"id": "gid://shopify/Order/1", "name": "#1", "cancelledAt": None, "closedAt": None, "note": None, "poNumber": None, "tags": ["old"], "customAttributes": []}
    client = SequenceClient([{"data": {"order": before}}])
    ops = ShopifyOperations(client)
    payload = {"id": before["id"], "tags": ["new"]}
    proposal = await ops.prepare_order_update(payload)
    assert any("integralmente" in warning for warning in proposal["warnings"])
    with pytest.raises(ConfirmationError):
        await ops.update_order({"id": before["id"], "tags": ["other"], "confirmationToken": proposal["confirmationToken"]})
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_order_update_apply_uses_order_input():
    before = {"id": "gid://shopify/Order/1", "name": "#1", "cancelledAt": None, "closedAt": None, "note": None, "poNumber": None, "tags": [], "customAttributes": []}
    client = SequenceClient([{"data": {"order": before}}, {"data": {"orderUpdate": {"order": {**before, "note": "Separar"}, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    payload = {"id": before["id"], "note": "Separar"}
    proposal = await ops.prepare_order_update(payload)
    result = await ops.update_order({**payload, "confirmationToken": proposal["confirmationToken"]})
    assert client.calls[-1][1] == {"input": payload}
    assert result["operation"] == "orderUpdate"


@pytest.mark.asyncio
async def test_fulfillment_orders_missing_order_is_compact():
    client = SequenceClient([{"data": {"order": None}}])
    result = await ShopifyOperations(client).list_order_fulfillment_orders({"id": "gid://shopify/Order/1"})
    assert result == {"order": None, "items": [], "pageInfo": {}}


def cancellable_order():
    return {"id": "gid://shopify/Order/1", "name": "#1", "cancelledAt": None, "cancelReason": None, "test": False, "confirmed": True, "displayFinancialStatus": "PAID", "displayFulfillmentStatus": "UNFULFILLED", "currentTotalPriceSet": {"shopMoney": {"amount": "100.00", "currencyCode": "BRL"}}, "netPaymentSet": {"shopMoney": {"amount": "100.00", "currencyCode": "BRL"}}, "currentTotalRefundedSet": {"shopMoney": {"amount": "0.00", "currencyCode": "BRL"}}, "transactions": [], "fulfillmentOrders": {"nodes": []}, "returns": {"nodes": []}}


@pytest.mark.asyncio
async def test_order_cancel_is_irreversible_financial_and_destructive():
    client = SequenceClient([{"data": {"order": cancellable_order()}}, {"data": {"orderCancel": {"job": {"id": "gid://shopify/Job/1", "done": False}, "orderCancelUserErrors": []}}}])
    ops = ShopifyOperations(client)
    payload = {"orderId": "gid://shopify/Order/1", "reason": "CUSTOMER", "refundOriginalPaymentMethods": True, "restock": True, "notifyCustomer": True, "staffNote": "Solicitado pelo cliente"}
    proposal = await ops.prepare_order_cancel(payload)
    assert proposal["financial"] is True and proposal["irreversible"] is True
    result = await ops.cancel_order({**payload, "confirmationToken": proposal["confirmationToken"]})
    assert result["operation"] == "orderCancel"
    assert BY_NAME["shopify_cancel_order"].tool.annotations.destructiveHint is True


@pytest.mark.asyncio
async def test_order_cancel_rejects_active_return_before_token():
    order = cancellable_order()
    order["returns"] = {"nodes": [{"id": "gid://shopify/Return/1", "name": "R1", "status": "OPEN", "totalQuantity": 1}]}
    client = SequenceClient([{"data": {"order": order}}])
    payload = {"orderId": order["id"], "reason": "CUSTOMER", "refundOriginalPaymentMethods": False, "restock": False, "notifyCustomer": False, "staffNote": "Teste"}
    with pytest.raises(ShopifyError, match="devolução ativa"):
        await ShopifyOperations(client).prepare_order_cancel(payload)
