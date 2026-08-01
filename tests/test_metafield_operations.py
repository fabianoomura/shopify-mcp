import pytest
from jsonschema import Draft202012Validator

from shopify_mcp.catalog import DEFINITIONS
from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)

    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    async def graphql(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


def owner(metafield):
    return {"id": "gid://shopify/Product/1", "__typename": "Product", "selected": metafield}


def item(digest):
    return {"ownerId": "gid://shopify/Product/1", "namespace": "mooui", "key": "erp_id", "type": "single_line_text_field", "value": "42", "compareDigest": digest}


def test_set_schema_requires_explicit_compare_digest():
    tool = next(entry.tool for entry in DEFINITIONS if entry.tool.name == "shopify_prepare_metafields_set")
    validator = Draft202012Validator(tool.inputSchema)
    validator.validate({"metafields": [item(None)]})
    invalid = item(None); del invalid["compareDigest"]
    with pytest.raises(Exception):
        validator.validate({"metafields": [invalid]})


@pytest.mark.asyncio
async def test_prepare_create_requires_null_digest_and_is_atomic():
    client = SequenceClient([{"data": {"item0": owner(None)}}])
    proposal = await ShopifyOperations(client).prepare_metafields_set({"metafields": [item(None)]})
    assert proposal["atomic"] is True
    assert "compareDigest" in client.calls[0][0]


@pytest.mark.asyncio
async def test_prepare_update_rejects_stale_digest():
    current = {"id": "gid://shopify/Metafield/2", "namespace": "mooui", "key": "erp_id", "type": "single_line_text_field", "value": "41", "compareDigest": "current"}
    with pytest.raises(ShopifyError, match="desatualizado"):
        await ShopifyOperations(SequenceClient([{"data": {"item0": owner(current)}}])).prepare_metafields_set({"metafields": [item("stale")]})


@pytest.mark.asyncio
async def test_delete_revalidates_digest_after_consuming_confirmation():
    old = {"id": "gid://shopify/Metafield/2", "namespace": "mooui", "key": "erp_id", "type": "single_line_text_field", "value": "41", "compareDigest": "old"}
    changed = {**old, "value": "99", "compareDigest": "new"}
    delete_item = {key: item("old")[key] for key in ("ownerId", "namespace", "key", "compareDigest")}
    client = SequenceClient([{"data": {"item0": owner(old)}}, {"data": {"item0": owner(changed)}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_metafields_delete({"metafields": [delete_item]})
    with pytest.raises(ShopifyError, match="mudou"):
        await ops.metafields_delete({"metafields": [delete_item], "confirmationToken": proposal["confirmationToken"]})
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_delete_strips_digest_from_shopify_input():
    current = {"id": "gid://shopify/Metafield/2", "namespace": "mooui", "key": "erp_id", "type": "single_line_text_field", "value": "41", "compareDigest": "same"}
    delete_item = {"ownerId": "gid://shopify/Product/1", "namespace": "mooui", "key": "erp_id", "compareDigest": "same"}
    responses = [{"data": {"item0": owner(current)}}, {"data": {"item0": owner(current)}}, {"data": {"metafieldsDelete": {"deletedMetafields": [{"ownerId": delete_item["ownerId"], "namespace": "mooui", "key": "erp_id"}], "userErrors": []}}}]
    client = SequenceClient(responses); ops = ShopifyOperations(client)
    proposal = await ops.prepare_metafields_delete({"metafields": [delete_item]})
    await ops.metafields_delete({"metafields": [delete_item], "confirmationToken": proposal["confirmationToken"]})
    assert "compareDigest" not in client.calls[-1][1]["metafields"][0]


@pytest.mark.asyncio
async def test_definition_create_checks_identifier_and_binds_complete_input():
    created = {"id": "gid://shopify/MetafieldDefinition/1", "name": "ERP ID"}
    client = SequenceClient([{"data": {"metafieldDefinition": None}}, {"data": {"metafieldDefinitionCreate": {"createdDefinition": created, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    request = {"name": "ERP ID", "namespace": "mooui", "key": "erp_id", "ownerType": "PRODUCT", "type": "single_line_text_field", "pin": True}
    proposal = await ops.prepare_metafield_definition_create(request)
    result = await ops.create_metafield_definition({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["createdDefinition"] == created
    assert client.calls[-1][1]["definition"] == request


@pytest.mark.asyncio
async def test_app_definition_delete_requires_deleting_values():
    definition = {"id": "gid://shopify/MetafieldDefinition/1", "name": "Private", "namespace": "$app:mooui", "key": "id", "description": None, "ownerType": "PRODUCT", "type": {"name": "single_line_text_field", "category": "TEXT"}, "pinnedPosition": None, "validations": [], "access": {"admin": "PRIVATE", "storefront": "NONE", "customerAccount": "NONE"}}
    with pytest.raises(ShopifyError, match="exigem"):
        await ShopifyOperations(SequenceClient([{"data": {"metafieldDefinition": definition}}])).prepare_metafield_definition_delete({"id": definition["id"], "deleteAllAssociatedMetafields": False})
