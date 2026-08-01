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


VARIANT_ID = "gid://shopify/ProductVariant/1"


def request(quantity=2):
    return {"lineItems": [{"variantId": VARIANT_ID, "quantity": quantity}], "customerId": "gid://shopify/Customer/2", "tags": ["agente"], "acceptAutomaticDiscounts": False}


def calculation(errors=None):
    variant = {"id": VARIANT_ID, "title": "P", "sku": "SKU", "availableForSale": True, "inventoryQuantity": 5, "product": {"id": "gid://shopify/Product/3", "title": "Produto", "status": "ACTIVE"}}
    return {"data": {"draftOrderCalculate": {"calculatedDraftOrder": {"totalPriceSet": {"shopMoney": {"amount": "20.00", "currencyCode": "BRL"}}, "lineItems": []}, "userErrors": errors or []}, "nodes": [variant]}}


@pytest.mark.asyncio
async def test_draft_create_is_calculated_and_bound_to_exact_input():
    client = SequenceClient([calculation(), {"data": {"draftOrderCreate": {"draftOrder": {"id": "gid://shopify/DraftOrder/4", "name": "#D1"}, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_draft_order_create(request())
    result = await ops.create_draft_order({**request(), "confirmationToken": proposal["confirmationToken"]})
    assert "draftOrderCalculate" in client.calls[0][0]
    assert client.calls[1][1] == {"input": request()}
    assert result["operation"] == "draftOrderCreate"


@pytest.mark.asyncio
async def test_draft_token_rejects_changed_quantity():
    client = SequenceClient([calculation()])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_draft_order_create(request())
    with pytest.raises(ConfirmationError):
        await ops.create_draft_order({**request(quantity=3), "confirmationToken": proposal["confirmationToken"]})
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_draft_rejects_missing_variant():
    response = calculation()
    response["data"]["nodes"] = [None]
    with pytest.raises(ShopifyError, match="Variantes não encontradas"):
        await ShopifyOperations(SequenceClient([response])).prepare_draft_order_create(request())


@pytest.mark.asyncio
async def test_draft_rejects_duplicate_variant_lines_before_api():
    client = SequenceClient([])
    invalid = request()
    invalid["lineItems"] = [invalid["lineItems"][0], {"variantId": VARIANT_ID, "quantity": 1}]
    with pytest.raises(ValueError, match="Cada variante"):
        await ShopifyOperations(client).prepare_draft_order_create(invalid)


@pytest.mark.asyncio
async def test_invoice_send_requires_exact_previewed_recipient():
    preview = {"data": {"draftOrderInvoicePreview": {"previewHtml": "<p>Olá</p>", "previewSubject": "#D1", "userErrors": []}, "draftOrder": {"id": "gid://shopify/DraftOrder/4", "name": "#D1", "status": "OPEN", "email": "a@example.com", "invoiceSentAt": None, "totalPriceSet": {}}}}
    client = SequenceClient([preview])
    ops = ShopifyOperations(client)
    args = {"id": "gid://shopify/DraftOrder/4", "email": {"to": "a@example.com", "subject": "Pedido"}}
    proposal = await ops.prepare_draft_order_invoice_send(args)
    with pytest.raises(ConfirmationError):
        await ops.send_draft_order_invoice({"id": args["id"], "email": {"to": "b@example.com", "subject": "Pedido"}, "confirmationToken": proposal["confirmationToken"]})
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_complete_rejects_already_completed_draft():
    response = {"data": {"draftOrder": {"id": "gid://shopify/DraftOrder/4", "name": "#D1", "status": "COMPLETED", "completedAt": "2026-01-01T00:00:00Z", "email": None, "currencyCode": "BRL", "totalPriceSet": {}, "lineItems": {"nodes": []}, "order": {"id": "gid://shopify/Order/5", "name": "#1"}}}}
    with pytest.raises(ShopifyError, match="já foi concluído"):
        await ShopifyOperations(SequenceClient([response])).prepare_draft_order_complete({"id": "gid://shopify/DraftOrder/4"})


@pytest.mark.asyncio
async def test_delete_uses_nested_input_and_one_time_confirmation():
    preview = {"data": {"draftOrder": {"id": "gid://shopify/DraftOrder/4", "name": "#D1", "status": "OPEN", "completedAt": None, "invoiceSentAt": None, "email": None, "totalPriceSet": {}, "order": None}}}
    deleted = {"data": {"draftOrderDelete": {"deletedId": "gid://shopify/DraftOrder/4", "userErrors": []}}}
    client = SequenceClient([preview, deleted])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_draft_order_delete({"id": "gid://shopify/DraftOrder/4"})
    result = await ops.delete_draft_order({"id": "gid://shopify/DraftOrder/4", "confirmationToken": proposal["confirmationToken"]})
    assert client.calls[-1][1] == {"input": {"id": "gid://shopify/DraftOrder/4"}}
    assert result["deletedId"] == "gid://shopify/DraftOrder/4"
    with pytest.raises(ConfirmationError):
        await ops.delete_draft_order({"id": "gid://shopify/DraftOrder/4", "confirmationToken": proposal["confirmationToken"]})
