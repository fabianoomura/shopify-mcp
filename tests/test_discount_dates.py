import pytest

from shopify_mcp.catalog import enabled_definitions
from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.confirmations import ConfirmationError
from shopify_mcp.operations import DISCOUNT_DATES_NODE, ShopifyOperations

CODE = "gid://shopify/DiscountCodeNode/1"
AUTO = "gid://shopify/DiscountAutomaticNode/2"


class Client:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


def nodes():
    return {"data": {"nodes": [
        {"id": CODE, "codeDiscount": {"__typename": "DiscountCodeBasic", "title": "SARRIA10", "status": "ACTIVE", "startsAt": "2025-08-13T10:12:35Z", "endsAt": None}},
        {"id": AUTO, "automaticDiscount": {"__typename": "DiscountAutomaticBxgy", "title": "3x2 Sheets", "status": "ACTIVE", "startsAt": "2026-10-20T17:25:00Z", "endsAt": None}},
    ]}}


@pytest.mark.asyncio
async def test_dates_update_previews_before_after_and_routes_by_type():
    code_ok = {"data": {"discountCodeBasicUpdate": {"codeDiscountNode": {"id": CODE, "codeDiscount": {"title": "SARRIA10", "endsAt": "2026-11-30T23:00:00Z"}}, "userErrors": []}}}
    auto_ok = {"data": {"discountAutomaticBxgyUpdate": {"automaticDiscountNode": {"id": AUTO, "automaticDiscount": {"title": "3x2 Sheets", "endsAt": "2026-11-30T23:00:00Z"}}, "userErrors": []}}}
    client = Client(nodes(), nodes(), code_ok, auto_ok)
    ops = ShopifyOperations(client)
    request = {"ids": [CODE, AUTO], "endsAt": "2026-11-30T23:00:00Z"}
    proposal = await ops.prepare_discount_dates_update(request)
    assert proposal["count"] == 2
    assert proposal["changes"][0]["before"] == {"startsAt": "2025-08-13T10:12:35Z", "endsAt": None}
    assert proposal["changes"][1]["after"] == {"startsAt": "2026-10-20T17:25:00Z", "endsAt": "2026-11-30T23:00:00Z"}
    result = await ops.update_discount_dates({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["updated"] == 2 and result["failed"] == 0
    assert "discountCodeBasicUpdate(id:$id,basicCodeDiscount:$input)" in client.calls[2][0]
    assert "$input:DiscountCodeBasicInput!" in client.calls[2][0]
    assert "discountAutomaticBxgyUpdate(id:$id,automaticBxgyDiscount:$input)" in client.calls[3][0]
    assert client.calls[3][1] == {"id": AUTO, "input": {"endsAt": "2026-11-30T23:00:00Z"}}


@pytest.mark.asyncio
async def test_dates_update_reports_individual_failures():
    code_err = {"data": {"discountCodeBasicUpdate": {"codeDiscountNode": None, "userErrors": [{"field": ["endsAt"], "message": "invalid", "code": "INVALID"}]}}}
    auto_ok = {"data": {"discountAutomaticBxgyUpdate": {"automaticDiscountNode": {"id": AUTO, "automaticDiscount": {"title": "3x2 Sheets"}}, "userErrors": []}}}
    ops = ShopifyOperations(Client(nodes(), nodes(), code_err, auto_ok))
    request = {"ids": [CODE, AUTO], "endsAt": None}
    proposal = await ops.prepare_discount_dates_update(request)
    assert any("endsAt=null" in warning for warning in proposal["warnings"])
    result = await ops.update_discount_dates({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["success"] is False
    assert result["failed"] == 1 and result["results"][0]["title"] == "SARRIA10"


@pytest.mark.asyncio
async def test_dates_token_binds_dates_and_ids():
    ops = ShopifyOperations(Client(nodes()))
    proposal = await ops.prepare_discount_dates_update({"ids": [CODE, AUTO], "endsAt": "2026-11-30T23:00:00Z"})
    with pytest.raises(ConfirmationError):
        await ops.update_discount_dates({"ids": [CODE, AUTO], "endsAt": "2026-12-31T23:00:00Z", "confirmationToken": proposal["confirmationToken"]})
    with pytest.raises(ConfirmationError):
        await ops.update_discount_dates({"ids": [CODE], "endsAt": "2026-11-30T23:00:00Z", "confirmationToken": proposal["confirmationToken"]})


@pytest.mark.asyncio
async def test_dates_rejects_end_before_current_start_and_missing_ids():
    with pytest.raises(ValueError, match="3x2 Sheets"):
        await ShopifyOperations(Client(nodes())).prepare_discount_dates_update({"ids": [CODE, AUTO], "endsAt": "2026-01-01T00:00:00Z"})
    with pytest.raises(ShopifyError, match="não encontrados"):
        await ShopifyOperations(Client({"data": {"nodes": [None]}})).prepare_discount_dates_update({"ids": [CODE], "endsAt": None})


def test_dates_requires_a_date_and_valid_range():
    with pytest.raises(ValueError, match="startsAt e/ou endsAt"):
        ShopifyOperations._discount_dates_args({"ids": [CODE]})
    with pytest.raises(ValueError, match="posterior"):
        ShopifyOperations._discount_dates_args({"ids": [CODE], "startsAt": "2026-11-01T00:00:00Z", "endsAt": "2026-10-01T00:00:00Z"})


def test_dates_fragment_balanced_and_tool_in_catalog():
    assert DISCOUNT_DATES_NODE.count("{") == DISCOUNT_DATES_NODE.count("}")
    assert "shopify_update_discount_dates" in {item.tool.name for item in enabled_definitions("catalog", True)}
