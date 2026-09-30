import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.confirmations import ConfirmationError
from shopify_mcp.operations import ShopifyOperations


PRODUCT = {
    "id": "gid://shopify/Product/1", "title": "Camiseta", "handle": "camiseta",
    "options": [
        {"id": "gid://shopify/ProductOption/10", "name": "Cor", "position": 1,
         "optionValues": [{"id": "gid://shopify/ProductOptionValue/100", "name": "Azul", "hasVariants": True}]},
        {"id": "gid://shopify/ProductOption/20", "name": "Tamanho", "position": 2,
         "optionValues": [{"id": "gid://shopify/ProductOptionValue/200", "name": "M", "hasVariants": True}]},
    ],
    "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/1", "title": "Azul / M"}]},
}


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_options_create_prepare_and_apply():
    client = SequenceClient([
        {"data": {"product": PRODUCT}},
        {"data": {"productOptionsCreate": {"product": PRODUCT, "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    args = {"productId": PRODUCT["id"], "options": [{"name": "Material", "values": [{"name": "Algodão"}]}], "variantStrategy": "CREATE"}
    preview = await ops.prepare_product_options_create(args)
    assert preview["warnings"]
    result = await ops.product_options_create({**args, "confirmationToken": preview["confirmationToken"]})
    assert result["operation"] == "productOptionsCreate"


@pytest.mark.asyncio
async def test_option_update_rejects_value_from_another_option():
    client = SequenceClient([{"data": {"product": PRODUCT}}])
    args = {"productId": PRODUCT["id"], "optionId": "gid://shopify/ProductOption/10", "valuesToUpdate": [{"id": "gid://shopify/ProductOptionValue/200", "name": "G"}], "variantStrategy": "LEAVE_AS_IS"}
    with pytest.raises(ShopifyError, match="não pertencem"):
        await ShopifyOperations(client).prepare_product_option_update(args)


@pytest.mark.asyncio
async def test_options_delete_position_has_destructive_warning_and_exact_token():
    client = SequenceClient([{"data": {"product": PRODUCT}}])
    ops = ShopifyOperations(client)
    args = {"productId": PRODUCT["id"], "optionIds": ["gid://shopify/ProductOption/20"], "strategy": "POSITION"}
    preview = await ops.prepare_product_options_delete(args)
    assert any("apagar variantes" in warning for warning in preview["warnings"])
    with pytest.raises(ConfirmationError, match="exatamente"):
        await ops.product_options_delete({**args, "strategy": "DEFAULT", "confirmationToken": preview["confirmationToken"]})
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_options_reorder_requires_complete_option_and_value_sets():
    client = SequenceClient([{"data": {"product": PRODUCT}}, {"data": {"product": PRODUCT}}])
    ops = ShopifyOperations(client)
    with pytest.raises(ValueError, match="cada opção atual"):
        await ops.prepare_product_options_reorder({"productId": PRODUCT["id"], "options": [{"id": "gid://shopify/ProductOption/10"}]})
    with pytest.raises(ValueError, match="cada valor atual"):
        await ops.prepare_product_options_reorder({"productId": PRODUCT["id"], "options": [{"id": "gid://shopify/ProductOption/20"}, {"id": "gid://shopify/ProductOption/10", "values": [{"id": "gid://shopify/ProductOptionValue/999"}]}]})


@pytest.mark.asyncio
async def test_option_update_manage_applies_exact_graphql_contract():
    client = SequenceClient([
        {"data": {"product": PRODUCT}},
        {"data": {"productOptionUpdate": {"product": PRODUCT, "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    args = {"productId": PRODUCT["id"], "optionId": "gid://shopify/ProductOption/10", "valuesToAdd": [{"name": "Verde"}], "variantStrategy": "MANAGE"}
    preview = await ops.prepare_product_option_update(args)
    result = await ops.product_option_update({**args, "confirmationToken": preview["confirmationToken"]})
    query, variables = client.calls[-1]
    assert "ProductOptionUpdateVariantStrategy!" in query
    assert variables["optionValuesToAdd"] == [{"name": "Verde"}]
    assert result["operation"] == "productOptionUpdate"


def _rename_node(pid, oid, name):
    return {"id": f"gid://shopify/Product/{pid}", "title": f"P{pid}", "handle": f"p{pid}", "options": [{"id": f"gid://shopify/ProductOption/{oid}", "name": name}]}


def _item(pid, oid):
    return {"productId": f"gid://shopify/Product/{pid}", "optionId": f"gid://shopify/ProductOption/{oid}"}


@pytest.mark.asyncio
async def test_options_rename_classifies_and_applies_only_ready_items():
    client = SequenceClient([
        {"data": {"nodes": [_rename_node(1, 10, "Cor"), _rename_node(2, 20, "Estampa"), _rename_node(3, 30, "Tamanho"), None]}},
        {"data": {"productOptionUpdate": {"product": _rename_node(1, 10, "Estampa"), "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    items = [_item(1, 10), _item(2, 20), _item(3, 30), _item(4, 40)]
    preview = await ops.prepare_product_options_rename({"fromName": "Cor", "toName": "Estampa", "items": items})
    assert preview["summary"] == {"requested": 4, "ready": 1, "alreadyRenamed": 1, "skipped": 2, "withValueChanges": 0}
    assert preview["applyItems"] == [_item(1, 10)]
    result = await ops.product_options_rename({"fromName": "Cor", "toName": "Estampa", "items": preview["applyItems"], "confirmationToken": preview["confirmationToken"]})
    assert result["summary"] == {"requested": 1, "renamed": 1, "errors": 0}
    query, variables = client.calls[-1]
    assert variables == {"productId": "gid://shopify/Product/1", "option": {"id": "gid://shopify/ProductOption/10", "name": "Estampa"}, "variantStrategy": "LEAVE_AS_IS"}
    assert "optionValuesToAdd" not in query


@pytest.mark.asyncio
async def test_options_rename_token_bound_to_exact_items():
    client = SequenceClient([{"data": {"nodes": [_rename_node(1, 10, "Cor"), _rename_node(2, 20, "Cor")]}}])
    ops = ShopifyOperations(client)
    preview = await ops.prepare_product_options_rename({"fromName": "Cor", "toName": "Estampa", "items": [_item(1, 10), _item(2, 20)]})
    with pytest.raises(ConfirmationError):
        await ops.product_options_rename({"fromName": "Cor", "toName": "Estampa", "items": [_item(1, 10)], "confirmationToken": preview["confirmationToken"]})
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_options_rename_continues_after_item_error():
    client = SequenceClient([
        {"data": {"nodes": [_rename_node(1, 10, "Cor"), _rename_node(2, 20, "Cor")]}},
        {"data": {"productOptionUpdate": {"product": None, "userErrors": [{"field": ["option"], "message": "boom", "code": "X"}]}}},
        {"data": {"productOptionUpdate": {"product": _rename_node(2, 20, "Estampa"), "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    preview = await ops.prepare_product_options_rename({"fromName": "Cor", "toName": "Estampa", "items": [_item(1, 10), _item(2, 20)]})
    result = await ops.product_options_rename({"fromName": "Cor", "toName": "Estampa", "items": preview["applyItems"], "confirmationToken": preview["confirmationToken"]})
    assert result["summary"] == {"requested": 2, "renamed": 1, "errors": 1}
    assert result["success"] is False and result["errors"][0]["productId"] == "gid://shopify/Product/1"


@pytest.mark.asyncio
async def test_options_rename_rejects_same_name_and_duplicates_without_api_call():
    client = SequenceClient([])
    ops = ShopifyOperations(client)
    with pytest.raises(ValueError, match="diferentes"):
        await ops.prepare_product_options_rename({"fromName": "Cor", "toName": "Cor", "items": [_item(1, 10)]})
    with pytest.raises(ValueError, match="apenas uma vez"):
        await ops.prepare_product_options_rename({"fromName": "Cor", "toName": "Estampa", "items": [_item(1, 10), _item(1, 11)]})
    assert client.calls == []


@pytest.mark.asyncio
async def test_options_rename_without_ready_items_issues_no_token():
    client = SequenceClient([{"data": {"nodes": [_rename_node(2, 20, "Estampa")]}}])
    preview = await ShopifyOperations(client).prepare_product_options_rename({"fromName": "Cor", "toName": "Estampa", "items": [_item(2, 20)]})
    assert preview["summary"]["ready"] == 0 and "confirmationToken" not in preview


def _valued_node(pid, oid, name, values):
    return {"id": f"gid://shopify/Product/{pid}", "title": f"P{pid}", "handle": f"p{pid}", "options": [{"id": f"gid://shopify/ProductOption/{oid}", "name": name, "optionValues": [{"id": f"gid://shopify/ProductOptionValue/{vid}", "name": vname} for vid, vname in values]}]}


@pytest.mark.asyncio
async def test_options_rename_with_value_renames_sends_values_and_checks_them():
    renames = {"2.80 M": "0,53 x 2,80", "10.00 M": "0,53 x 10,00"}
    client = SequenceClient([
        {"data": {"nodes": [_valued_node(1, 10, "Tamanho", [(100, "2.80 M"), (101, "10.00 M")]), _valued_node(2, 20, "Metragem", [(200, "0,53 x 2,80")])]}},
        {"data": {"productOptionUpdate": {"product": _valued_node(1, 10, "Metragem", [(100, "0,53 x 2,80"), (101, "0,53 x 10,00")]), "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    preview = await ops.prepare_product_options_rename({"fromName": "Tamanho", "toName": "Metragem", "items": [_item(1, 10), _item(2, 20)], "valueRenames": renames})
    assert preview["summary"]["ready"] == 1 and preview["summary"]["alreadyRenamed"] == 1 and preview["summary"]["withValueChanges"] == 1
    item = preview["applyItems"][0]
    assert item["valuesToUpdate"] == [{"id": "gid://shopify/ProductOptionValue/100", "name": "0,53 x 2,80"}, {"id": "gid://shopify/ProductOptionValue/101", "name": "0,53 x 10,00"}]
    result = await ops.product_options_rename({"fromName": "Tamanho", "toName": "Metragem", "items": preview["applyItems"], "confirmationToken": preview["confirmationToken"]})
    assert result["summary"] == {"requested": 1, "renamed": 1, "errors": 0}
    assert client.calls[-1][1]["optionValuesToUpdate"] == item["valuesToUpdate"]


@pytest.mark.asyncio
async def test_options_rename_skips_when_values_would_collide():
    client = SequenceClient([{"data": {"nodes": [_valued_node(1, 10, "Tamanho", [(100, "0.53M"), (101, "2.80 M")])]}}])
    preview = await ShopifyOperations(client).prepare_product_options_rename({"fromName": "Tamanho", "toName": "Metragem", "items": [_item(1, 10)], "valueRenames": {"0.53M": "0,53 x 2,80", "2.80 M": "0,53 x 2,80"}})
    assert preview["summary"]["ready"] == 0 and preview["summary"]["skipped"] == 1
    assert "confirmationToken" not in preview


@pytest.mark.asyncio
async def test_options_rename_per_item_value_renames_same_option_name():
    client = SequenceClient([
        {"data": {"nodes": [_valued_node(1, 10, "Tamanho", [(100, "U")]), _valued_node(2, 20, "Tamanho", [(200, "U")]), _valued_node(3, 30, "Tamanho", [(300, "P")])]}},
        {"data": {"productOptionUpdate": {"product": _valued_node(1, 10, "Tamanho", [(100, "17 x 260 cm")]), "userErrors": []}}},
        {"data": {"productOptionUpdate": {"product": _valued_node(2, 20, "Tamanho", [(200, "48 x 68 cm")]), "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    items = [{**_item(1, 10), "valueRenames": {"U": "17 x 260 cm"}}, {**_item(2, 20), "valueRenames": {"U": "48 x 68 cm"}}, {**_item(3, 30), "valueRenames": {"U": "30 x 40 cm"}}]
    preview = await ops.prepare_product_options_rename({"fromName": "Tamanho", "toName": "Tamanho", "items": items})
    assert preview["summary"]["ready"] == 2 and preview["summary"]["alreadyRenamed"] == 1
    assert [item["valuesToUpdate"][0]["name"] for item in preview["applyItems"]] == ["17 x 260 cm", "48 x 68 cm"]
    assert all("valueRenames" not in item for item in preview["applyItems"])
    result = await ops.product_options_rename({"fromName": "Tamanho", "toName": "Tamanho", "items": preview["applyItems"], "confirmationToken": preview["confirmationToken"]})
    assert result["summary"] == {"requested": 2, "renamed": 2, "errors": 0}


def _u_node(pid, size_values, variants=1, with_estampa=True):
    options = [{"id": f"gid://shopify/ProductOption/{pid}0", "name": "Tamanho", "optionValues": [{"id": f"gid://shopify/ProductOptionValue/{pid}0{i}", "name": v} for i, v in enumerate(size_values)]}]
    if with_estampa:
        options.append({"id": f"gid://shopify/ProductOption/{pid}1", "name": "Estampa", "optionValues": [{"id": f"gid://shopify/ProductOptionValue/{pid}10", "name": "Lua"}]})
    return {"id": f"gid://shopify/Product/{pid}", "title": f"P{pid}", "options": options, "variantsCount": {"count": variants}}


def _u_item(pid):
    return {"productId": f"gid://shopify/Product/{pid}", "optionId": f"gid://shopify/ProductOption/{pid}0"}


def _u_deleted(pid, variants):
    return {"data": {"productOptionsDelete": {"deletedOptionsIds": [f"gid://shopify/ProductOption/{pid}0"], "product": {"id": f"gid://shopify/Product/{pid}", "options": [{"id": f"gid://shopify/ProductOption/{pid}1", "name": "Estampa"}], "variantsCount": {"count": variants}}, "userErrors": []}}}


U_ARGS = {"optionName": "Tamanho", "onlyValue": "U"}


@pytest.mark.asyncio
async def test_options_delete_batch_only_single_value_and_checks_variants():
    client = SequenceClient([
        {"data": {"nodes": [_u_node(1, ["U"]), _u_node(2, ["U", "P"], variants=2), _u_node(3, ["U"], with_estampa=False), _u_node(4, ["U"])]}},
        {"data": {"nodes": [_u_node(1, ["U"]), _u_node(4, ["U"])]}},
        _u_deleted(1, 1),
        _u_deleted(4, 0),
    ])
    ops = ShopifyOperations(client)
    preview = await ops.prepare_product_options_delete_batch({**U_ARGS, "items": [_u_item(1), _u_item(2), _u_item(3), _u_item(4)]})
    assert preview["summary"] == {"requested": 4, "ready": 2, "skipped": 2}
    assert preview["applyItems"] == [_u_item(1), _u_item(4)]
    result = await ops.product_options_delete_batch({**U_ARGS, "items": preview["applyItems"], "confirmationToken": preview["confirmationToken"]})
    assert result["summary"] == {"requested": 2, "deleted": 1, "errors": 1}
    assert "variantes mudou" in result["errors"][0]["error"]
    assert "strategy:DEFAULT" in client.calls[-1][0]
    assert client.calls[-1][1] == {"productId": "gid://shopify/Product/4", "options": ["gid://shopify/ProductOption/40"]}


@pytest.mark.asyncio
async def test_options_delete_batch_token_bound_to_exact_items():
    client = SequenceClient([{"data": {"nodes": [_u_node(1, ["U"]), _u_node(2, ["U"])]}}])
    ops = ShopifyOperations(client)
    preview = await ops.prepare_product_options_delete_batch({**U_ARGS, "items": [_u_item(1), _u_item(2)]})
    with pytest.raises(ConfirmationError):
        await ops.product_options_delete_batch({**U_ARGS, "items": [_u_item(1)], "confirmationToken": preview["confirmationToken"]})
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_options_delete_batch_skips_option_changed_since_prepare():
    client = SequenceClient([
        {"data": {"nodes": [_u_node(1, ["U"])]}},
        {"data": {"nodes": [_u_node(1, ["U", "G"])]}},
    ])
    ops = ShopifyOperations(client)
    preview = await ops.prepare_product_options_delete_batch({**U_ARGS, "items": [_u_item(1)]})
    result = await ops.product_options_delete_batch({**U_ARGS, "items": preview["applyItems"], "confirmationToken": preview["confirmationToken"]})
    assert result["summary"] == {"requested": 1, "deleted": 0, "errors": 1}
    assert len(client.calls) == 2
