import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    async def graphql(self, query, variables=None):
        self.calls.append((query, variables)); return self.responses.pop(0)


DEFINITION = {"id": "gid://shopify/MetaobjectDefinition/1", "name": "Size Chart", "type": "size_chart", "displayNameKey": "title", "fieldDefinitions": [{"key": "title", "name": "Title", "required": True, "type": {"name": "single_line_text_field"}}, {"key": "body", "name": "Body", "required": False, "type": {"name": "multi_line_text_field"}}]}


def test_definition_rejects_duplicate_keys_and_invalid_display_name():
    base = {"name": "X", "type": "size_chart", "displayNameKey": "missing", "fieldDefinitions": [{"key": "title", "name": "Title", "type": "single_line_text_field", "required": True}]}
    with pytest.raises(ValueError, match="displayNameKey"):
        ShopifyOperations._validate_metaobject_definition(base)
    base["displayNameKey"] = "title"; base["fieldDefinitions"].append(dict(base["fieldDefinitions"][0]))
    with pytest.raises(ValueError, match="única"):
        ShopifyOperations._validate_metaobject_definition(base)


@pytest.mark.asyncio
async def test_create_requires_all_required_schema_fields():
    client = SequenceClient([{"data": {"metaobjectDefinitionByType": DEFINITION}}])
    with pytest.raises(ShopifyError, match="obrigatórios"):
        await ShopifyOperations(client).prepare_metaobject_create({"type": "size_chart", "fields": [{"key": "body", "value": "x"}]})


@pytest.mark.asyncio
async def test_create_validates_handle_conflict_and_binds_fields():
    client = SequenceClient([{"data": {"metaobjectDefinitionByType": DEFINITION}}, {"data": {"metaobjectByHandle": None}}, {"data": {"metaobjectCreate": {"metaobject": {"id": "gid://shopify/Metaobject/2"}, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    request = {"type": "size_chart", "handle": "queen", "fields": [{"key": "title", "value": "Queen"}]}
    proposal = await ops.prepare_metaobject_create(request)
    result = await ops.create_metaobject({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["operation"] == "metaobjectCreate"
    assert client.calls[-1][1]["metaobject"] == request


@pytest.mark.asyncio
async def test_update_rejects_redirect_without_handle():
    current = {"id": "gid://shopify/Metaobject/2", "type": "size_chart", "handle": "queen", "fields": [], "definition": {"type": "size_chart"}}
    with pytest.raises(ValueError, match="exige"):
        await ShopifyOperations(SequenceClient([{"data": {"metaobject": current}}])).prepare_metaobject_update({"id": current["id"], "redirectNewHandle": True})


@pytest.mark.asyncio
async def test_delete_is_confirmation_bound():
    current = {"id": "gid://shopify/Metaobject/2", "type": "size_chart", "handle": "queen", "fields": []}
    client = SequenceClient([{"data": {"metaobject": current}}, {"data": {"metaobjectDelete": {"deletedId": current["id"], "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_metaobject_delete({"id": current["id"]})
    result = await ops.delete_metaobject({"id": current["id"], "confirmationToken": proposal["confirmationToken"]})
    assert result["deletedId"] == current["id"]


def test_definition_update_prevents_orphan_display_name_and_unacknowledged_loss():
    args = {"id": DEFINITION["id"], "fieldDefinitions": [{"delete": {"key": "title"}}], "acknowledgeFieldDataLoss": True}
    with pytest.raises(ValueError, match="displayNameKey"):
        ShopifyOperations._validate_metaobject_field_operations(DEFINITION, args)
    args["displayNameKey"] = "body"; args["acknowledgeFieldDataLoss"] = False
    with pytest.raises(ShopifyError, match="acknowledge"):
        ShopifyOperations._validate_metaobject_field_operations(DEFINITION, args)


@pytest.mark.asyncio
async def test_definition_update_strips_local_acknowledgement_from_api_input():
    updated = {**DEFINITION, "description": "Updated"}
    client = SequenceClient([{"data": {"metaobjectDefinition": DEFINITION}}, {"data": {"metaobjectDefinitionUpdate": {"metaobjectDefinition": updated, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    request = {"id": DEFINITION["id"], "description": "Updated", "acknowledgeFieldDataLoss": False}
    proposal = await ops.prepare_metaobject_definition_update(request)
    await ops.update_metaobject_definition({**request, "confirmationToken": proposal["confirmationToken"]})
    assert "acknowledgeFieldDataLoss" not in client.calls[-1][1]["definition"]


@pytest.mark.asyncio
async def test_definition_delete_requires_explicit_cascade_and_binds_it():
    with pytest.raises(ShopifyError, match="confirmCascade"):
        await ShopifyOperations(SequenceClient([])).prepare_metaobject_definition_delete({"id": DEFINITION["id"], "confirmCascade": False})
    definition = {**DEFINITION, "metaobjectsCount": 3}
    client = SequenceClient([{"data": {"metaobjectDefinition": definition}}, {"data": {"metaobjectDefinitionDelete": {"deletedId": DEFINITION["id"], "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_metaobject_definition_delete({"id": DEFINITION["id"], "confirmCascade": True})
    result = await ops.delete_metaobject_definition({"id": DEFINITION["id"], "confirmCascade": True, "confirmationToken": proposal["confirmationToken"]})
    assert result["deletedId"] == DEFINITION["id"]
