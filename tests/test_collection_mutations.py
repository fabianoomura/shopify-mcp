import pytest

from shopify_mcp.catalog import BY_NAME
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


COLLECTION = {"id": "gid://shopify/Collection/1", "title": "Verão", "descriptionHtml": "", "handle": "verao", "sortOrder": "MANUAL", "templateSuffix": None, "seo": {"title": "Verão", "description": ""}, "productsCount": {"count": 2}, "sources": []}


@pytest.mark.asyncio
async def test_collection_create_is_modern_and_unpublished():
    client = SequenceClient([{"data": {"collectionCreate": {"collection": COLLECTION, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    payload = {"title": "Verão", "sortOrder": "MANUAL"}
    proposal = await ops.prepare_collection_create(payload)
    assert "sem publicação" in proposal["warnings"][0]
    result = await ops.create_collection({**payload, "confirmationToken": proposal["confirmationToken"]})
    query, variables = client.calls[-1]
    assert "CollectionCreateInput!" in query
    assert "collectionCreate(collection:$collection)" in query
    assert variables == {"collection": payload}
    assert result["operation"] == "collectionCreate"


@pytest.mark.asyncio
async def test_collection_delete_preview_is_irreversible_and_tool_is_destructive():
    client = SequenceClient([
        {"data": {"collection": {**COLLECTION, "publications": {"nodes": [{"id": "gid://shopify/Publication/1", "name": "Online Store"}]}}}},
        {"data": {"collectionDelete": {"deletedCollectionId": COLLECTION["id"], "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_collection_delete({"id": COLLECTION["id"]})
    assert proposal["irreversible"] is True
    result = await ops.delete_collection({"id": COLLECTION["id"], "confirmationToken": proposal["confirmationToken"]})
    assert result["deletedCollectionId"] == COLLECTION["id"]
    assert BY_NAME["shopify_delete_collection"].tool.annotations.destructiveHint is True


@pytest.mark.asyncio
async def test_product_membership_rejects_same_collection_join_and_leave_without_api_call():
    client = SequenceClient([])
    payload = {"id": "gid://shopify/Product/1", "collectionsToJoin": [COLLECTION["id"]], "collectionsToLeave": [COLLECTION["id"]]}
    with pytest.raises(ValueError, match="mesma coleção"):
        await ShopifyOperations(client).prepare_product_update(payload)
    assert client.calls == []


RULE_SET_AND = {"appliedDisjunctively": False, "rules": [{"column": "TAG", "relation": "EQUALS", "condition": "roupa_de_cama"}]}


@pytest.mark.asyncio
async def test_collection_update_sends_rule_set_and_reads_current_rules():
    automated = {**COLLECTION, "ruleSet": RULE_SET_AND}
    client = SequenceClient([
        {"data": {"collection": automated}},
        {"data": {"collectionUpdate": {"collection": automated, "job": {"id": "gid://shopify/Job/1", "done": False}, "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    nova = {"appliedDisjunctively": False, "rules": [
        {"column": "TAG", "relation": "EQUALS", "condition": "roupa_de_cama"},
        {"column": "TAG", "relation": "NOT_EQUALS", "condition": "Estampa adulto"},
    ]}
    payload = {"id": COLLECTION["id"], "ruleSet": nova}
    proposal = await ops.prepare_collection_update(payload)
    assert proposal["before"]["ruleSet"] == RULE_SET_AND
    assert proposal["after"]["ruleSet"] == nova
    assert proposal["willChange"] is True
    assert any("assíncrona" in w for w in proposal["warnings"])
    assert not any("ATENÇÃO" in w for w in proposal["warnings"])
    preview_query, _ = client.calls[0]
    assert "ruleSet{appliedDisjunctively rules{column relation condition}}" in preview_query
    await ops.update_collection({**payload, "confirmationToken": proposal["confirmationToken"]})
    query, variables = client.calls[-1]
    assert "CollectionUpdateInput!" in query
    assert variables == {"collection": {"id": COLLECTION["id"], "ruleSet": nova}}


@pytest.mark.asyncio
async def test_collection_update_warns_when_negative_rule_is_disjunctive():
    client = SequenceClient([{"data": {"collection": {**COLLECTION, "ruleSet": {"appliedDisjunctively": True, "rules": [{"column": "TITLE", "relation": "CONTAINS", "condition": "Fronha"}]}}}}])
    ops = ShopifyOperations(client)
    proposal = await ShopifyOperations(client).prepare_collection_update({"id": COLLECTION["id"], "ruleSet": {"appliedDisjunctively": True, "rules": [
        {"column": "TITLE", "relation": "CONTAINS", "condition": "Fronha"},
        {"column": "TAG", "relation": "NOT_EQUALS", "condition": "Estampa adulto"},
    ]}})
    assert proposal["warnings"][0].startswith("ATENÇÃO")
    assert "INCLUI todo produto" in proposal["warnings"][0]
    assert "MESMA coluna" not in " ".join(proposal["warnings"])


@pytest.mark.asyncio
async def test_collection_update_warns_when_current_rules_may_be_a_grouped_admin_condition():
    """Caso real (fronhas, 22/09): o admin agrupou "Fronha OU Travesseiro de Berço"; a API devolve duas regras soltas iguais a E."""
    atual = {"appliedDisjunctively": False, "rules": [
        {"column": "TITLE", "relation": "CONTAINS", "condition": "Fronha"},
        {"column": "TITLE", "relation": "CONTAINS", "condition": "Travesseiro de Berço"},
        {"column": "TAG", "relation": "NOT_EQUALS", "condition": "Estampa adulto"},
    ]}
    client = SequenceClient([{"data": {"collection": {**COLLECTION, "ruleSet": atual}}}])
    proposal = await ShopifyOperations(client).prepare_collection_update({"id": COLLECTION["id"], "ruleSet": atual})
    assert proposal["warnings"][0].startswith("ATENÇÃO: a regra atual repete TITLE CONTAINS")
    assert "103 para 0" in proposal["warnings"][0]


@pytest.mark.asyncio
async def test_collection_update_does_not_flag_two_different_tags_as_grouped():
    """TAG ate_15_off + TAG Roupa de Cama é E de verdade (28 produtos), mas o guarda não tem como saber — só alerta relação repetida."""
    atual = {"appliedDisjunctively": False, "rules": [
        {"column": "TITLE", "relation": "CONTAINS", "condition": "Edredom"},
        {"column": "TITLE", "relation": "NOT_CONTAINS", "condition": "Jogo"},
    ]}
    client = SequenceClient([{"data": {"collection": {**COLLECTION, "ruleSet": atual}}}])
    proposal = await ShopifyOperations(client).prepare_collection_update({"id": COLLECTION["id"], "ruleSet": {**atual, "rules": atual["rules"] + [{"column": "TAG", "relation": "NOT_EQUALS", "condition": "Estampa adulto"}]}})
    assert not any("regra atual repete" in w for w in proposal["warnings"])


@pytest.mark.asyncio
async def test_collection_rule_set_rejects_relation_not_allowed_for_column_without_api_call():
    client = SequenceClient([])
    with pytest.raises(ValueError, match="não é aceita para TAG"):
        await ShopifyOperations(client).prepare_collection_update({"id": COLLECTION["id"], "ruleSet": {"appliedDisjunctively": False, "rules": [{"column": "TAG", "relation": "CONTAINS", "condition": "x"}]}})
    assert client.calls == []


@pytest.mark.asyncio
async def test_collection_rule_set_rejects_duplicate_rule_without_api_call():
    client = SequenceClient([])
    rule = {"column": "TAG", "relation": "EQUALS", "condition": "fronha"}
    with pytest.raises(ValueError, match="Regra repetida"):
        await ShopifyOperations(client).prepare_collection_update({"id": COLLECTION["id"], "ruleSet": {"appliedDisjunctively": False, "rules": [rule, dict(rule)]}})
    assert client.calls == []


@pytest.mark.asyncio
async def test_collection_update_warns_when_manual_collection_becomes_automated():
    client = SequenceClient([{"data": {"collection": {**COLLECTION, "ruleSet": None}}}])
    proposal = await ShopifyOperations(client).prepare_collection_update({"id": COLLECTION["id"], "ruleSet": RULE_SET_AND})
    assert "manual hoje" in proposal["warnings"][0]


@pytest.mark.asyncio
async def test_collection_create_accepts_rule_set():
    created = {**COLLECTION, "ruleSet": RULE_SET_AND}
    client = SequenceClient([{"data": {"collectionCreate": {"collection": created, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    payload = {"title": "Automática", "ruleSet": RULE_SET_AND}
    proposal = await ops.prepare_collection_create(payload)
    assert "membership vem da regra" in proposal["warnings"][0]
    await ops.create_collection({**payload, "confirmationToken": proposal["confirmationToken"]})
    _, variables = client.calls[-1]
    assert variables == {"collection": payload}


def test_collection_tools_expose_rule_set_schema():
    for name in ("shopify_prepare_collection_update", "shopify_update_collection", "shopify_prepare_collection_create", "shopify_create_collection"):
        schema = BY_NAME[name].tool.inputSchema["properties"]["ruleSet"]
        assert schema["required"] == ["appliedDisjunctively", "rules"]
        assert "TAG" in schema["properties"]["rules"]["items"]["properties"]["column"]["enum"]
