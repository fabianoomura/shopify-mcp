import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.confirmations import ConfirmationError
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True, financial_limits_brl=(("refund", "100.00"),))

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


def order_response(refundable=2):
    money = lambda amount: {"shopMoney": {"amount": amount, "currencyCode": "BRL"}, "presentmentMoney": {"amount": amount, "currencyCode": "BRL"}}
    return {"data": {"order": {
        "id": "gid://shopify/Order/1", "name": "#1", "cancelledAt": None, "displayFinancialStatus": "PAID", "currencyCode": "BRL", "presentmentCurrencyCode": "BRL",
        "lineItems": {"nodes": [{"id": "gid://shopify/LineItem/1", "name": "Produto", "sku": "SKU", "quantity": 2, "refundableQuantity": refundable, "restockable": True, "unfulfilledQuantity": 0}]},
        "suggestedRefund": {"amountSet": money("50.00"), "maximumRefundableSet": money("100.00"), "subtotalSet": money("45.00"), "totalTaxSet": money("5.00"), "refundLineItems": [], "suggestedTransactions": [{"kind": "REFUND", "gateway": "shopify_payments", "formattedGateway": "Shopify Payments", "amountSet": money("50.00"), "maximumRefundableSet": money("100.00"), "parentTransaction": {"id": "gid://shopify/OrderTransaction/9"}}]},
    }}}


def payload(quantity=1):
    return {"orderId": "gid://shopify/Order/1", "lineItems": [{"lineItemId": "gid://shopify/LineItem/1", "quantity": quantity, "restockType": "NO_RESTOCK"}], "notifyCustomer": False, "note": "Devolução parcial"}


@pytest.mark.asyncio
async def test_refund_uses_shopify_suggestion_and_required_idempotency():
    client = SequenceClient([order_response(), {"data": {"refundCreate": {"order": {"id": "gid://shopify/Order/1"}, "refund": {"id": "gid://shopify/Refund/1"}, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_refund_create(payload())
    assert proposal["transactions"][0]["amount"] == "50.00"
    apply = {**payload(), "transactions": proposal["transactions"], "currency": proposal["currency"], "idempotencyKey": proposal["idempotencyKey"], "confirmationToken": proposal["confirmationToken"]}
    result = await ops.create_refund(apply)
    query, variables = client.calls[-1]
    assert "@idempotent(key:$idempotencyKey)" in query
    assert variables["input"]["allowOverRefunding"] is False
    assert result["operation"] == "refundCreate"


@pytest.mark.asyncio
async def test_refund_rejects_quantity_above_refundable():
    client = SequenceClient([order_response(refundable=1)])
    with pytest.raises(ShopifyError, match="saldo reembolsável"):
        await ShopifyOperations(client).prepare_refund_create(payload(quantity=2))


@pytest.mark.asyncio
async def test_refund_token_binds_calculated_transactions():
    client = SequenceClient([order_response()])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_refund_create(payload())
    changed = [{**proposal["transactions"][0], "amount": "49.00"}]
    with pytest.raises(ConfirmationError):
        await ops.create_refund({**payload(), "transactions": changed, "currency": proposal["currency"], "idempotencyKey": proposal["idempotencyKey"], "confirmationToken": proposal["confirmationToken"]})
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_refund_restock_requires_location_before_api_call():
    client = SequenceClient([])
    invalid = payload()
    invalid["lineItems"][0]["restockType"] = "RETURN"
    with pytest.raises(ValueError, match="exigem locationId"):
        await ShopifyOperations(client).prepare_refund_create(invalid)
