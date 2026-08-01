import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    async def graphql(self, query, variables=None): self.calls.append((query, variables)); return self.responses.pop(0)


def request():
    return {"name": "Brazil", "handle": "brazil", "status": "DRAFT", "conditions": {"regionsCondition": {"regions": [{"countryCode": "BR"}]}}, "currencySettings": {"baseCurrency": "BRL", "localCurrencies": False}, "makeDuplicateUniqueMarketsDraft": False}


def test_market_rejects_duplicate_regions_and_conflicting_currency_action():
    duplicated = request(); duplicated["conditions"]["regionsCondition"]["regions"].append({"countryCode": "BR"})
    with pytest.raises(ValueError, match="countryCode"):
        ShopifyOperations._validate_market_input(duplicated)
    conflicting = {"currencySettings": {"baseCurrency": "BRL", "localCurrencies": False}, "removeCurrencySettings": True}
    with pytest.raises(ValueError, match="não pode"):
        ShopifyOperations._validate_market_input(conflicting)


@pytest.mark.asyncio
async def test_market_create_checks_handle_and_uses_modern_status():
    created = {"id": "gid://shopify/Market/1", "name": "Brazil", "handle": "brazil", "status": "DRAFT"}
    client = SequenceClient([{"data": {"markets": {"nodes": []}}}, {"data": {"marketCreate": {"market": created, "userErrors": []}}}])
    ops = ShopifyOperations(client); proposal = await ops.prepare_market_create(request())
    result = await ops.market_create({**request(), "confirmationToken": proposal["confirmationToken"]})
    assert result["market"] == created
    assert "enabled" not in client.calls[-1][1]["input"]


@pytest.mark.asyncio
async def test_market_update_rejects_catalog_in_both_sets():
    catalog = "gid://shopify/MarketCatalog/2"
    with pytest.raises(ValueError, match="adicionado e removido"):
        ShopifyOperations._validate_market_input({"catalogsToAdd": [catalog], "catalogsToDelete": [catalog]})


@pytest.mark.asyncio
async def test_market_update_is_confirmation_bound():
    current = {"id": "gid://shopify/Market/1", "name": "Brazil", "handle": "brazil", "status": "DRAFT", "regions": {"nodes": []}, "catalogs": {"nodes": []}}
    updated = {**current, "status": "ACTIVE"}
    client = SequenceClient([{"data": {"market": current}}, {"data": {"marketUpdate": {"market": updated, "userErrors": []}}}])
    ops = ShopifyOperations(client); request_update = {"id": current["id"], "status": "ACTIVE"}
    proposal = await ops.prepare_market_update(request_update)
    result = await ops.market_update({**request_update, "confirmationToken": proposal["confirmationToken"]})
    assert result["market"]["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_market_delete_requires_assignment_acknowledgement():
    with pytest.raises(ShopifyError, match="confirmAssignmentsRemoval"):
        await ShopifyOperations(SequenceClient([])).prepare_market_delete({"id": "gid://shopify/Market/1", "confirmAssignmentsRemoval": False})
