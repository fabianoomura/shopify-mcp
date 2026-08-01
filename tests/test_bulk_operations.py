import pytest

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


def test_bulk_documents_are_curated_and_escape_search_input():
    document = ShopifyOperations._bulk_export_document({"resource": "PRODUCTS", "query": 'title:"x" } mutation { shop { id }'})
    assert "bulkOperationRunQuery" not in document
    assert '\\"x\\"' in document
    assert document.startswith("{products(")


def test_bulk_metaobjects_require_type_and_reject_it_elsewhere():
    with pytest.raises(ValueError, match="obrigatório"):
        ShopifyOperations._bulk_export_document({"resource": "METAOBJECTS"})
    with pytest.raises(ValueError, match="só pode"):
        ShopifyOperations._bulk_export_document({"resource": "PRODUCTS", "metaobjectType": "spec"})


@pytest.mark.asyncio
async def test_bulk_export_confirmation_binds_exact_options():
    created = {"id": "gid://shopify/BulkOperation/1", "type": "QUERY", "status": "CREATED"}
    client = SequenceClient([{"data": {"bulkOperationRunQuery": {"bulkOperation": created, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    request = {"resource": "PRODUCTS", "query": "status:active", "groupObjects": False}
    proposal = await ops.prepare_bulk_export(request)
    result = await ops.start_bulk_export({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["bulkOperation"] == created
    assert client.calls[0][1]["groupObjects"] is False
    assert "products(query:\"status:active\")" in client.calls[0][1]["query"]
    with pytest.raises(ValueError):
        await ops.start_bulk_export({**request, "groupObjects": True, "confirmationToken": proposal["confirmationToken"]})


@pytest.mark.asyncio
async def test_cancel_only_active_job_and_uses_confirmation():
    completed = {"id": "gid://shopify/BulkOperation/1", "status": "COMPLETED"}
    with pytest.raises(ShopifyError, match="CREATED ou RUNNING"):
        await ShopifyOperations(SequenceClient([{"data": {"bulkOperation": completed}}])).prepare_bulk_operation_cancel({"id": completed["id"]})

    running = {"id": "gid://shopify/BulkOperation/2", "status": "RUNNING", "type": "QUERY"}
    canceled = {**running, "status": "CANCELING"}
    client = SequenceClient([{"data": {"bulkOperation": running}}, {"data": {"bulkOperationCancel": {"bulkOperation": canceled, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_bulk_operation_cancel({"id": running["id"]})
    result = await ops.cancel_bulk_operation({"id": running["id"], "confirmationToken": proposal["confirmationToken"]})
    assert result["bulkOperation"]["status"] == "CANCELING"


@pytest.mark.asyncio
async def test_bulk_import_uses_only_curated_mutation_and_binds_declared_hash():
    created = {"id": "gid://shopify/BulkOperation/9", "type": "MUTATION", "status": "CREATED"}
    client = SequenceClient([{"data": {"bulkOperationRunMutation": {"bulkOperation": created, "userErrors": []}}}])
    ops = ShopifyOperations(client)
    request = {"kind": "PRODUCT_UPDATE", "stagedUploadPath": "tmp/1/bulk/job/input.jsonl", "clientIdentifier": "sync-2026-07-21", "lineCount": 3, "sha256": "a" * 64, "acknowledgeUnorderedExecution": True}
    proposal = await ops.prepare_bulk_import(request)
    assert proposal["variablesPerJsonlLine"] == {"product": "ProductUpdateInput!"}
    result = await ops.start_bulk_import({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["bulkOperation"] == created
    variables = client.calls[0][1]
    assert variables["mutation"] == ops._BULK_IMPORT_MUTATIONS["PRODUCT_UPDATE"]
    assert variables["stagedUploadPath"] == request["stagedUploadPath"]


@pytest.mark.asyncio
async def test_bulk_import_stage_has_fixed_media_contract():
    target = {"url": "https://shopify-staged-uploads.storage.googleapis.com", "resourceUrl": None, "parameters": [{"name": "key", "value": "tmp/1/input"}]}
    client = SequenceClient([{"data": {"stagedUploadsCreate": {"stagedTargets": [target], "userErrors": []}}}])
    ops = ShopifyOperations(client)
    request = {"filename": "input.jsonl", "fileSize": "120"}
    proposal = await ops.prepare_bulk_import_staged_upload(request)
    result = await ops.create_bulk_import_staged_upload({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["stagedTargets"] == [target]
    staged = client.calls[0][1]["input"][0]
    assert staged == {"filename": "input.jsonl", "mimeType": "text/jsonl", "resource": "BULK_MUTATION_VARIABLES", "httpMethod": "POST", "fileSize": "120"}
