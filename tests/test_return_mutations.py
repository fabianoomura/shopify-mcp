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


def preview_response(quantity=2, include_reason=True):
    reason = {"id": "gid://shopify/ReturnReasonDefinition/9", "name": "Tamanho incorreto"}
    return {"data": {
        "order": {"id": "gid://shopify/Order/1", "name": "#1", "cancelledAt": None},
        "returnableFulfillments": {"nodes": [{
            "id": "gid://shopify/ReturnableFulfillment/2",
            "fulfillment": {"id": "gid://shopify/Fulfillment/3", "status": "SUCCESS", "location": {"id": "gid://shopify/Location/4", "name": "CD"}},
            "returnableFulfillmentLineItems": {"nodes": [{"quantity": quantity, "fulfillmentLineItem": {"id": "gid://shopify/FulfillmentLineItem/5", "quantity": 2, "lineItem": {"id": "gid://shopify/LineItem/6", "name": "Camiseta", "sku": "CAM-P"}}}]},
        }]},
        "nodes": [reason if include_reason else None],
    }}


def payload(quantity=1):
    return {"orderId": "gid://shopify/Order/1", "returnLineItems": [{
        "fulfillmentLineItemId": "gid://shopify/FulfillmentLineItem/5",
        "quantity": quantity,
        "returnReasonDefinitionId": "gid://shopify/ReturnReasonDefinition/9",
        "returnReasonNote": "Cliente solicitou troca",
    }]}


@pytest.mark.asyncio
async def test_return_uses_modern_reason_definition_and_exact_confirmation():
    client = SequenceClient([preview_response(), {"data": {"returnCreate": {"return": {"id": "gid://shopify/Return/7", "status": "OPEN"}, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_return_create(payload())
    result = await ops.create_return({**payload(), "confirmationToken": proposal["confirmationToken"]})
    query, variables = client.calls[-1]
    assert "returnReasonDefinitionId" in variables["returnInput"]["returnLineItems"][0]
    assert "returnReason:" not in query
    assert result["operation"] == "returnCreate"


@pytest.mark.asyncio
async def test_return_rejects_quantity_above_returnable():
    client = SequenceClient([preview_response(quantity=1)])
    with pytest.raises(ShopifyError, match="saldo devolvível"):
        await ShopifyOperations(client).prepare_return_create(payload(quantity=2))


@pytest.mark.asyncio
async def test_return_rejects_unknown_reason_definition():
    client = SequenceClient([preview_response(include_reason=False)])
    with pytest.raises(ShopifyError, match="Motivos de devolução inválidos"):
        await ShopifyOperations(client).prepare_return_create(payload())


@pytest.mark.asyncio
async def test_return_token_binds_quantity_and_reason():
    client = SequenceClient([preview_response()])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_return_create(payload())
    with pytest.raises(ConfirmationError):
        await ops.create_return({**payload(quantity=2), "confirmationToken": proposal["confirmationToken"]})
    assert len(client.calls) == 1
