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


COND_SOURCE = {"__typename": "CollectionConditionsSource", "id": "gid://shopify/CollectionConditionsSource/9", "title": "Regras", "inclusion": {"matchType": "ALL", "conditions": [{"__typename": "CollectionSourceInclusionConditionProductTag", "id": "c1"}], "selections": {"nodes": []}}}
MANUAL_SOURCE = {"__typename": "CollectionConditionsSource", "id": "gid://shopify/CollectionConditionsSource/8", "title": "Manual", "inclusion": {"matchType": None, "conditions": [], "selections": {"nodes": [{"product": {"id": "gid://shopify/Product/5"}}]}}}


@pytest.mark.asyncio
async def test_collection_update_replaces_condition_source_with_converted_rules():
    automated = {**COLLECTION, "ruleSet": RULE_SET_AND, "sources": [COND_SOURCE]}
    client = SequenceClient([
        {"data": {"collection": automated}},
        {"data": {"collection": automated}},
        {"data": {"collectionUpdate": {"collection": automated, "job": {"id": "gid://shopify/Job/1", "done": False}, "userErrors": []}}},
    ])
    ops = ShopifyOperations(client)
    nova = {"appliedDisjunctively": False, "rules": [
        {"column": "TAG", "relation": "EQUALS", "condition": "roupa_de_cama"},
        {"column": "TAG", "relation": "NOT_EQUALS", "condition": "Estampa adulto"},
        {"column": "TITLE", "relation": "NOT_CONTAINS", "condition": "Jogo"},
    ]}
    payload = {"id": COLLECTION["id"], "ruleSet": nova}
    proposal = await ops.prepare_collection_update(payload)
    assert proposal["before"]["ruleSet"] == RULE_SET_AND
    assert proposal["sourcesToReplace"] == [COND_SOURCE["id"]]
    assert any("substituída" in w for w in proposal["warnings"])
    await ops.update_collection({**payload, "confirmationToken": proposal["confirmationToken"]})
    query, variables = client.calls[-1]
    assert "CollectionUpdateInput!" in query and "ruleSet" not in variables["collection"]
    sent = variables["collection"]
    assert sent["sourcesToDelete"] == [COND_SOURCE["id"]]
    inclusion = sent["sourcesToCreate"][0]["source"]["inclusion"]
    assert inclusion["matchType"] == "ALL"
    assert inclusion["conditions"] == [
        {"productTag": {"relation": "TAGGED_WITH", "values": ["roupa_de_cama"], "matchType": "ANY"}},
        {"productTag": {"relation": "NOT_TAGGED_WITH", "values": ["Estampa adulto"], "matchType": "ALL"}},
        {"productTitle": {"relation": "DOES_NOT_CONTAIN", "values": ["Jogo"], "matchType": "ALL"}},
    ]


@pytest.mark.asyncio
async def test_collection_update_on_manual_collection_keeps_selection_source():
    manual = {**COLLECTION, "ruleSet": None, "sources": [MANUAL_SOURCE]}
    client = SequenceClient([{"data": {"collection": manual}}, {"data": {"collection": manual}}, {"data": {"collectionUpdate": {"collection": manual, "job": None, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    payload = {"id": COLLECTION["id"], "ruleSet": {"appliedDisjunctively": False, "rules": [{"column": "TYPE", "relation": "EQUALS", "condition": "Adesivo de Interruptor"}]}}
    proposal = await ops.prepare_collection_update(payload)
    assert proposal["sourcesToReplace"] == []
    assert "continuam" in proposal["warnings"][0]
    await ops.update_collection({**payload, "confirmationToken": proposal["confirmationToken"]})
    sent = client.calls[-1][1]["collection"]
    assert "sourcesToDelete" not in sent
    assert sent["sourcesToCreate"][0]["source"]["inclusion"]["conditions"] == [{"productType": {"relation": "EQUALS", "values": ["Adesivo de Interruptor"], "matchType": "ANY"}}]


@pytest.mark.asyncio
async def test_collection_update_refuses_to_drop_condition_source_with_manual_picks():
    mixed = {**COND_SOURCE, "inclusion": {**COND_SOURCE["inclusion"], "selections": {"nodes": [{"product": {"id": "gid://shopify/Product/5"}}]}}}
    client = SequenceClient([{"data": {"collection": {**COLLECTION, "ruleSet": RULE_SET_AND, "sources": [mixed]}}}])
    with pytest.raises(ValueError, match="escolhidos à mão"):
        await ShopifyOperations(client).prepare_collection_update({"id": COLLECTION["id"], "ruleSet": RULE_SET_AND})


@pytest.mark.asyncio
async def test_collection_create_with_sub_collections_and_metafield_rule():
    client = SequenceClient([{"data": {"collectionCreate": {"collection": COLLECTION, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    payload = {"title": "Cozinha", "subCollectionIds": ["gid://shopify/Collection/2", "gid://shopify/Collection/3"],
               "ruleSet": {"appliedDisjunctively": True, "rules": [{"column": "METAFIELD_STRING_LIST", "relation": "EQUALS", "condition": "Floral", "definitionId": "gid://shopify/MetafieldDefinition/7"}, {"column": "VARIANT_COMPARE_AT_PRICE", "relation": "IS_SET", "condition": ""}]}}
    proposal = await ops.prepare_collection_create(payload)
    await ops.create_collection({**payload, "confirmationToken": proposal["confirmationToken"]})
    sent = client.calls[-1][1]["collection"]
    assert "ruleSet" not in sent and "subCollectionIds" not in sent
    source, sub = sent["sources"]
    assert source["source"]["inclusion"]["matchType"] == "ANY"
    assert source["source"]["inclusion"]["conditions"] == [
        {"metafieldStringList": {"definitionId": "gid://shopify/MetafieldDefinition/7", "relation": "INCLUDES", "values": ["Floral"], "matchType": "ANY"}},
        {"variantCompareAtPrice": {"relation": "IS_SET"}},
    ]
    assert sub == {"subCollections": {"title": "Subcoleções (MCP)", "collectionIds": ["gid://shopify/Collection/2", "gid://shopify/Collection/3"]}}


def test_sub_collections_split_in_sources_of_ten():
    from shopify_mcp.operations import _sub_collections_sources
    ids = [f"gid://shopify/Collection/{n}" for n in range(13)]
    first, second = _sub_collections_sources(ids)
    assert first["subCollections"]["collectionIds"] == ids[:10]
    assert second["subCollections"]["collectionIds"] == ids[10:]
    assert second["subCollections"]["title"] == "Subcoleções (MCP) 2/2"


@pytest.mark.asyncio
async def test_metafield_rule_requires_definition_id_without_api_call():
    client = SequenceClient([])
    with pytest.raises(ValueError, match="definitionId"):
        await ShopifyOperations(client).prepare_collection_create({"title": "x", "ruleSet": {"appliedDisjunctively": False, "rules": [{"column": "METAFIELD_STRING_LIST", "relation": "EQUALS", "condition": "Floral"}]}})
    assert client.calls == []


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
async def test_collection_create_converts_rule_set_to_conditions_source():
    created = {**COLLECTION, "ruleSet": RULE_SET_AND}
    client = SequenceClient([{"data": {"collectionCreate": {"collection": created, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    payload = {"title": "Automática", "ruleSet": RULE_SET_AND}
    proposal = await ops.prepare_collection_create(payload)
    assert "membership vem da regra" in proposal["warnings"][0]
    await ops.create_collection({**payload, "confirmationToken": proposal["confirmationToken"]})
    _, variables = client.calls[-1]
    assert variables == {"collection": {"title": "Automática", "sources": [{"source": {"title": "Condições (MCP)", "inclusion": {"matchType": "ALL", "conditions": [{"productTag": {"relation": "TAGGED_WITH", "values": ["roupa_de_cama"], "matchType": "ANY"}}]}}}]}}


def test_collection_tools_expose_rule_set_schema():
    for name in ("shopify_prepare_collection_update", "shopify_update_collection", "shopify_prepare_collection_create", "shopify_create_collection"):
        schema = BY_NAME[name].tool.inputSchema["properties"]["ruleSet"]
        assert schema["required"] == ["appliedDisjunctively", "rules"]
        assert "TAG" in schema["properties"]["rules"]["items"]["properties"]["column"]["enum"]
