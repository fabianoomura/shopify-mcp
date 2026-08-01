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


def preview(quantity=10, tracked=True):
    return {"data": {"nodes": [{"id": "gid://shopify/InventoryItem/1", "sku": "SKU-1", "tracked": tracked, "inventoryLevels": {"nodes": [{"location": {"id": "gid://shopify/Location/2", "name": "CD", "isActive": True}, "quantities": [{"name": "available", "quantity": quantity}]}]}}]}}


def args(expected=10):
    return {"name": "available", "reason": "correction", "referenceDocumentUri": "gid://mooui/InventoryTransaction/TX-1", "changes": [{"inventoryItemId": "gid://shopify/InventoryItem/1", "locationId": "gid://shopify/Location/2", "delta": -2, "changeFromQuantity": expected}]}


@pytest.mark.asyncio
async def test_inventory_adjust_uses_cas_and_shopify_idempotency():
    client = SequenceClient([preview(), {"data": {"inventoryAdjustQuantities": {"inventoryAdjustmentGroup": {"changes": [{"name": "available", "delta": -2}]}, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_inventory_adjust(args())
    assert proposal["beforeAfter"][0]["after"] == 8
    result = await ops.inventory_adjust({**args(), "idempotencyKey": proposal["idempotencyKey"], "confirmationToken": proposal["confirmationToken"]})
    query, variables = client.calls[-1]
    assert "@idempotent(key:$idempotencyKey)" in query
    assert variables["input"]["changes"][0]["changeFromQuantity"] == 10
    assert result["idempotencyKey"] == proposal["idempotencyKey"]


@pytest.mark.asyncio
async def test_inventory_preview_rejects_stale_quantity():
    client = SequenceClient([preview(quantity=9)])
    with pytest.raises(ShopifyError, match="desatualizada"):
        await ShopifyOperations(client).prepare_inventory_adjust(args(expected=10))


@pytest.mark.asyncio
async def test_inventory_token_binds_idempotency_key():
    client = SequenceClient([preview()])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_inventory_adjust(args())
    with pytest.raises(ConfirmationError):
        await ops.inventory_adjust({**args(), "idempotencyKey": "00000000-0000-4000-8000-000000000000", "confirmationToken": proposal["confirmationToken"]})
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_inventory_rejects_untracked_item():
    client = SequenceClient([preview(tracked=False)])
    with pytest.raises(ShopifyError, match="rastreamento"):
        await ShopifyOperations(client).prepare_inventory_adjust(args())


@pytest.mark.asyncio
async def test_inventory_deactivation_warns_about_quantity_loss_and_applies():
    response = {"data": {
        "inventoryItem": {"id": "gid://shopify/InventoryItem/1", "sku": "SKU-1", "tracked": True, "inventoryLevels": {"nodes": [{"location": {"id": "gid://shopify/Location/2", "name": "CD", "isActive": True}, "quantities": [{"name": "available", "quantity": 10}]}]}},
        "nodes": [{"id": "gid://shopify/Location/2", "name": "CD", "isActive": True}],
    }}
    client = SequenceClient([response, {"data": {"inventoryBulkToggleActivation": {"inventoryItem": {"id": "gid://shopify/InventoryItem/1"}, "inventoryLevels": [], "userErrors": []}}}])
    ops = ShopifyOperations(client)
    payload = {"inventoryItemId": "gid://shopify/InventoryItem/1", "updates": [{"locationId": "gid://shopify/Location/2", "activate": False}]}
    proposal = await ops.prepare_inventory_activation_toggle(payload)
    assert "remove todas" in proposal["warnings"][0]
    result = await ops.inventory_activation_toggle({**payload, "confirmationToken": proposal["confirmationToken"]})
    assert result["operation"] == "inventoryBulkToggleActivation"


@pytest.mark.asyncio
async def test_inventory_activation_rejects_inactive_location():
    response = {"data": {
        "inventoryItem": {"id": "gid://shopify/InventoryItem/1", "sku": "SKU-1", "tracked": True, "inventoryLevels": {"nodes": []}},
        "nodes": [{"id": "gid://shopify/Location/2", "name": "Antigo", "isActive": False}],
    }}
    client = SequenceClient([response])
    with pytest.raises(ShopifyError, match="local inativo"):
        await ShopifyOperations(client).prepare_inventory_activation_toggle({"inventoryItemId": "gid://shopify/InventoryItem/1", "updates": [{"locationId": "gid://shopify/Location/2", "activate": True}]})


def weight_preview(value=0.5, unit="KILOGRAMS", sku="SKU-1"):
    return {"data": {"inventoryItem": {"id": "gid://shopify/InventoryItem/1", "sku": sku, "tracked": True, "measurement": {"weight": {"value": value, "unit": unit}}, "variant": {"id": "gid://shopify/ProductVariant/9", "displayName": "P / Único", "product": {"id": "gid://shopify/Product/7", "title": "P"}}}}}


@pytest.mark.asyncio
async def test_weight_prepare_shows_before_after_and_applies():
    apply_resp = {"data": {"inventoryItemUpdate": {"inventoryItem": {"id": "gid://shopify/InventoryItem/1", "measurement": {"weight": {"value": 1.2, "unit": "KILOGRAMS"}}}, "userErrors": []}}}
    client = SequenceClient([weight_preview(), apply_resp])
    ops = ShopifyOperations(client)
    payload = {"inventoryItemId": "gid://shopify/InventoryItem/1", "weight": {"value": 1.2, "unit": "KILOGRAMS"}}
    proposal = await ops.prepare_inventory_item_weight_update(payload)
    assert proposal["before"] == {"value": 0.5, "unit": "KILOGRAMS"}
    assert proposal["after"] == {"value": 1.2, "unit": "KILOGRAMS"}
    assert proposal["willChange"] is True
    result = await ops.inventory_item_weight_update({**payload, "confirmationToken": proposal["confirmationToken"]})
    query, variables = client.calls[-1]
    assert "inventoryItemUpdate" in query
    assert variables["input"]["measurement"]["weight"] == {"value": 1.2, "unit": "KILOGRAMS"}
    assert result["success"] is True


@pytest.mark.asyncio
async def test_weight_token_binds_arguments():
    client = SequenceClient([weight_preview(sku=None)])
    ops = ShopifyOperations(client)
    payload = {"inventoryItemId": "gid://shopify/InventoryItem/1", "weight": {"value": 1.2, "unit": "KILOGRAMS"}}
    proposal = await ops.prepare_inventory_item_weight_update(payload)
    with pytest.raises(ConfirmationError):
        await ops.inventory_item_weight_update({"inventoryItemId": "gid://shopify/InventoryItem/1", "weight": {"value": 2.0, "unit": "KILOGRAMS"}, "confirmationToken": proposal["confirmationToken"]})
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_weight_prepare_rejects_missing_item():
    client = SequenceClient([{"data": {"inventoryItem": None}}])
    with pytest.raises(ShopifyError, match="não encontrado"):
        await ShopifyOperations(client).prepare_inventory_item_weight_update({"inventoryItemId": "gid://shopify/InventoryItem/404", "weight": {"value": 1.0, "unit": "KILOGRAMS"}})
