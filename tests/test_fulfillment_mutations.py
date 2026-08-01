import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


FO = {"id": "gid://shopify/FulfillmentOrder/1", "status": "OPEN", "requestStatus": "UNSUBMITTED", "order": {"id": "gid://shopify/Order/1", "name": "#1"}, "assignedLocation": {"name": "CD", "location": {"id": "gid://shopify/Location/1", "name": "CD"}}, "supportedActions": [{"action": "CREATE_FULFILLMENT"}], "lineItems": {"nodes": [{"id": "gid://shopify/FulfillmentOrderLineItem/1", "totalQuantity": 3, "remainingQuantity": 2, "lineItem": {"id": "gid://shopify/LineItem/1", "name": "Produto", "sku": "SKU"}}]}}


def payload(quantity=1):
    return {"groups": [{"fulfillmentOrderId": FO["id"], "lineItems": [{"id": "gid://shopify/FulfillmentOrderLineItem/1", "quantity": quantity}]}], "notifyCustomer": False, "tracking": {"company": "Transportadora", "numbers": ["ABC"], "urls": ["https://tracking.example/ABC"]}}


@pytest.mark.asyncio
async def test_fulfillment_create_validates_quantities_and_never_uses_implicit_all():
    client = SequenceClient([{"data": {"nodes": [FO]}}, {"data": {"fulfillmentCreate": {"fulfillment": {"id": "gid://shopify/Fulfillment/1"}, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_fulfillment_create(payload())
    result = await ops.create_fulfillment({**payload(), "confirmationToken": proposal["confirmationToken"]})
    variables = client.calls[-1][1]
    assert variables["fulfillment"]["lineItemsByFulfillmentOrder"][0]["fulfillmentOrderLineItems"] == [{"id": "gid://shopify/FulfillmentOrderLineItem/1", "quantity": 1}]
    assert result["operation"] == "fulfillmentCreate"


@pytest.mark.asyncio
async def test_fulfillment_create_rejects_quantity_above_remaining():
    client = SequenceClient([{"data": {"nodes": [FO]}}])
    with pytest.raises(ShopifyError, match="excede"):
        await ShopifyOperations(client).prepare_fulfillment_create(payload(quantity=3))


@pytest.mark.asyncio
async def test_tracking_requires_parallel_url_list():
    client = SequenceClient([])
    invalid = {"fulfillmentId": "gid://shopify/Fulfillment/1", "tracking": {"numbers": ["A", "B"], "urls": ["https://tracking.example/A"]}, "notifyCustomer": False}
    with pytest.raises(ValueError, match="mesma quantidade"):
        await ShopifyOperations(client).prepare_fulfillment_tracking_update(invalid)
    assert client.calls == []


@pytest.mark.asyncio
async def test_tracking_notification_is_explicit_and_warned():
    current = {"id": "gid://shopify/Fulfillment/1", "status": "SUCCESS", "order": {"id": "gid://shopify/Order/1", "name": "#1"}, "trackingInfo": []}
    client = SequenceClient([{"data": {"fulfillment": current}}])
    ops = ShopifyOperations(client)
    args = {"fulfillmentId": current["id"], "tracking": {"company": "UPS", "numbers": ["1Z"]}, "notifyCustomer": True}
    proposal = await ops.prepare_fulfillment_tracking_update(args)
    assert proposal["warnings"]
