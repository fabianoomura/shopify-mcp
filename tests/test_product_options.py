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
