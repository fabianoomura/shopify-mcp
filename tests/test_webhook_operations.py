import pytest

from shopify_mcp.client import ShopifyError
from shopify_mcp.config import Settings
from shopify_mcp.operations import ShopifyOperations


class SequenceClient:
    settings = Settings("test.myshopify.com", "secret", enable_writes=True)
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    async def graphql(self, query, variables=None): self.calls.append((query, variables)); return self.responses.pop(0)


@pytest.mark.parametrize("uri", ["https://localhost/hook", "https://127.0.0.1/hook", "https://10.0.0.1/hook", "https://user:pass@example.com/hook", "https://service.internal/hook"])
def test_webhook_rejects_local_private_or_credentialed_https(uri):
    with pytest.raises(ValueError):
        ShopifyOperations._validate_webhook_uri(uri)


def test_webhook_accepts_public_https_and_managed_brokers():
    for uri in ("https://hooks.example.com/shopify", "pubsub://project:topic", "arn:aws:events:us-east-1:123456789012:event-source/test/source"):
        ShopifyOperations._validate_webhook_uri(uri)


@pytest.mark.asyncio
async def test_webhook_create_detects_duplicate_and_documents_consumer_security():
    request = {"topic": "ORDERS_CREATE", "uri": "https://hooks.example.com/shopify", "format": "JSON"}
    duplicate = {"data": {"webhookSubscriptions": {"nodes": [{"id": "gid://shopify/WebhookSubscription/1", "topic": request["topic"], "uri": request["uri"]}]}}}
    with pytest.raises(ShopifyError, match="Já existe"):
        await ShopifyOperations(SequenceClient([duplicate])).prepare_webhook_create(request)
    empty = {"data": {"webhookSubscriptions": {"nodes": []}}}
    proposal = await ShopifyOperations(SequenceClient([empty])).prepare_webhook_create(request)
    assert any("Hmac" in item for item in proposal["consumerRequirements"])
    assert any("Event-Id" in item for item in proposal["consumerRequirements"])


@pytest.mark.asyncio
async def test_webhook_update_is_patch_and_confirmation_bound():
    current = {"id": "gid://shopify/WebhookSubscription/1", "topic": "ORDERS_CREATE", "uri": "https://old.example/hook", "format": "JSON"}
    updated = {**current, "uri": "https://new.example/hook"}
    client = SequenceClient([{"data": {"webhookSubscription": current}}, {"data": {"webhookSubscriptionUpdate": {"webhookSubscription": updated, "userErrors": []}}}])
    ops = ShopifyOperations(client); request = {"id": current["id"], "uri": updated["uri"]}
    proposal = await ops.prepare_webhook_update(request)
    result = await ops.webhook_update({**request, "confirmationToken": proposal["confirmationToken"]})
    assert result["webhookSubscription"] == updated
    assert client.calls[-1][1]["webhookSubscription"] == {"uri": updated["uri"]}
