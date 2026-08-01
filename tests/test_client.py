import httpx
import pytest

from shopify_mcp.client import ShopifyClient, ShopifyError, mutation_result
from shopify_mcp.config import Settings


@pytest.mark.asyncio
async def test_graphql_sends_token_and_returns_data():
    async def handler(request: httpx.Request):
        assert request.headers["X-Shopify-Access-Token"] == "secret"
        return httpx.Response(200, json={"data": {"shop": {"name": "MOOUI"}}})
    client = ShopifyClient(Settings("test.myshopify.com", "secret", max_retries=0), httpx.MockTransport(handler))
    assert (await client.graphql("{ shop { name } }"))["data"]["shop"]["name"] == "MOOUI"
    await client.close()


@pytest.mark.asyncio
async def test_http_error_redacts_token():
    async def handler(_: httpx.Request):
        return httpx.Response(401, text="bad token secret")
    client = ShopifyClient(Settings("test.myshopify.com", "secret", max_retries=0), httpx.MockTransport(handler))
    with pytest.raises(ShopifyError) as captured:
        await client.graphql("{ shop { name } }")
    assert "secret" not in str(captured.value.details)
    assert "[REDACTED]" in str(captured.value.details)
    await client.close()


@pytest.mark.asyncio
async def test_graphql_errors_are_not_silenced():
    async def handler(_: httpx.Request):
        return httpx.Response(200, json={"errors": [{"message": "Denied"}]})
    client = ShopifyClient(Settings("test.myshopify.com", "secret", max_retries=0), httpx.MockTransport(handler))
    with pytest.raises(ShopifyError, match="GraphQL"):
        await client.graphql("{ shop { name } }")
    await client.close()


def test_mutation_user_errors_are_not_silenced():
    payload = {"data": {"productUpdate": {"userErrors": [{"field": ["seo"], "message": "Invalid"}]}}}
    with pytest.raises(ShopifyError, match="rejeitou"):
        mutation_result(payload, "productUpdate")


@pytest.mark.asyncio
async def test_mutation_is_never_retried_after_5xx():
    calls = 0

    async def handler(_: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(503, headers={"X-Request-ID": "req-1"}, text="temporary")

    client = ShopifyClient(Settings("test.myshopify.com", "secret", max_retries=3), httpx.MockTransport(handler))
    with pytest.raises(ShopifyError, match="desconhecido") as captured:
        await client.graphql("mutation X { tagsAdd(id: \"x\", tags: [\"a\"]) { userErrors { message } } }")
    assert calls == 1
    assert captured.value.details == {"requestId": "req-1", "outcomeUnknown": True}
    await client.close()


@pytest.mark.asyncio
async def test_query_can_retry_after_5xx():
    calls = 0

    async def handler(_: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(503) if calls == 1 else httpx.Response(200, json={"data": {"shop": {"id": "1"}}})

    client = ShopifyClient(Settings("test.myshopify.com", "secret", max_retries=1), httpx.MockTransport(handler))
    assert (await client.graphql("query { shop { id } }"))["data"]["shop"]["id"] == "1"
    assert calls == 2
    await client.close()
