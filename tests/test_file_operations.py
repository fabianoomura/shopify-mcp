import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.confirmations import ConfirmationError
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    async def graphql(self, query, variables=None):
        self.calls.append((query, variables)); return self.responses.pop(0)


@pytest.mark.asyncio
async def test_file_create_warns_on_replace_and_token_binds_policy():
    request = {"files": [{"originalSource": "https://cdn.example/a.jpg", "filename": "a.jpg", "contentType": "IMAGE", "duplicateResolutionMode": "REPLACE"}]}
    ops = ShopifyOperations(SequenceClient([]))
    proposal = await ops.prepare_files_create(request)
    assert proposal["replacementCount"] == 1
    changed = {"files": [{**request["files"][0], "duplicateResolutionMode": "APPEND_UUID"}], "confirmationToken": proposal["confirmationToken"]}
    with pytest.raises(ConfirmationError):
        await ops.files_create(changed)


@pytest.mark.asyncio
async def test_file_update_rejects_reference_conflict():
    item = {"id": "gid://shopify/MediaImage/1", "referencesToAdd": ["gid://shopify/Product/2"], "referencesToRemove": ["gid://shopify/Product/2"]}
    with pytest.raises(ValueError, match="adicionado e removido"):
        await ShopifyOperations(SequenceClient([])).prepare_files_update({"files": [item]})


@pytest.mark.asyncio
async def test_file_update_validates_products_and_preserves_exact_input():
    file = {"id": "gid://shopify/MediaImage/1", "__typename": "MediaImage", "alt": "old", "fileStatus": "READY"}
    product = {"id": "gid://shopify/Product/2", "title": "P"}
    updated = {**file, "alt": "new"}
    client = SequenceClient([{"data": {"nodes": [file]}}, {"data": {"nodes": [product]}}, {"data": {"fileUpdate": {"files": [updated], "userErrors": []}}}])
    ops = ShopifyOperations(client)
    request = {"files": [{"id": file["id"], "alt": "new", "referencesToAdd": [product["id"]]}]}
    proposal = await ops.prepare_files_update(request)
    result = await ops.files_update({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["files"] == [updated]
    assert client.calls[-1][1] == request


@pytest.mark.asyncio
async def test_file_delete_requires_reference_acknowledgement():
    with pytest.raises(ShopifyError, match="confirmRemoveReferences"):
        await ShopifyOperations(SequenceClient([])).prepare_files_delete({"fileIds": ["gid://shopify/GenericFile/1"], "confirmRemoveReferences": False})


@pytest.mark.asyncio
async def test_file_delete_strips_local_acknowledgement_from_shopify():
    file = {"id": "gid://shopify/GenericFile/1", "__typename": "GenericFile", "fileStatus": "READY"}
    client = SequenceClient([{"data": {"nodes": [file]}}, {"data": {"fileDelete": {"deletedFileIds": [file["id"]], "userErrors": []}}}])
    ops = ShopifyOperations(client)
    request = {"fileIds": [file["id"]], "confirmRemoveReferences": True}
    proposal = await ops.prepare_files_delete(request)
    await ops.files_delete({**request, "confirmationToken": proposal["confirmationToken"]})
    assert client.calls[-1][1] == {"fileIds": [file["id"]]}


@pytest.mark.asyncio
async def test_staged_video_requires_size_and_never_accepts_local_path():
    ops = ShopifyOperations(SequenceClient([]))
    item = {"filename": "demo.mp4", "mimeType": "video/mp4", "resource": "VIDEO", "httpMethod": "POST"}
    with pytest.raises(ValueError, match="fileSize"):
        await ops.prepare_staged_uploads_create({"input": [item]})


@pytest.mark.asyncio
async def test_staged_upload_returns_two_step_instructions():
    item = {"filename": "demo.mp4", "mimeType": "video/mp4", "fileSize": "2048", "resource": "VIDEO", "httpMethod": "POST"}
    payload = {"data": {"stagedUploadsCreate": {"stagedTargets": [{"url": "https://upload.example", "resourceUrl": "https://resource.example", "parameters": []}], "userErrors": []}}}
    client = SequenceClient([payload]); ops = ShopifyOperations(client)
    proposal = await ops.prepare_staged_uploads_create({"input": [item]})
    assert len(proposal["nextSteps"]) == 2
    result = await ops.staged_uploads_create({"input": [item], "confirmationToken": proposal["confirmationToken"]})
    assert result["containsTemporaryCredentials"] is True
