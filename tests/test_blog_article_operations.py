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
async def test_blog_delete_requires_explicit_article_policy():
    blog = {"id": "gid://shopify/Blog/1", "title": "News", "handle": "news", "articles": {"nodes": [{"id": "gid://shopify/Article/2", "title": "A"}], "pageInfo": {"hasNextPage": False}}}
    with pytest.raises(ShopifyError, match="contém artigos"):
        await ShopifyOperations(SequenceClient([{"data": {"blog": blog}}])).prepare_blog_delete({"id": blog["id"], "allowDeleteWithArticles": False})


@pytest.mark.asyncio
async def test_blog_update_token_binds_comment_policy():
    current = {"id": "gid://shopify/Blog/1", "title": "News", "handle": "news", "commentPolicy": "CLOSED", "templateSuffix": None, "updatedAt": "x"}
    ops = ShopifyOperations(SequenceClient([{"data": {"blog": current}}]))
    proposal = await ops.prepare_blog_update({"id": current["id"], "commentPolicy": "MODERATED"})
    with pytest.raises(ConfirmationError):
        await ops.update_blog({"id": current["id"], "commentPolicy": "AUTO_PUBLISHED", "confirmationToken": proposal["confirmationToken"]})


@pytest.mark.asyncio
async def test_article_create_validates_blog_and_maps_author():
    blog = {"id": "gid://shopify/Blog/1", "title": "News", "handle": "news", "commentPolicy": "MODERATED"}
    preview = {"data": {"blog": blog, "articles": {"nodes": []}}}
    created = {"data": {"articleCreate": {"article": {"id": "gid://shopify/Article/2"}, "userErrors": []}}}
    client = SequenceClient([preview, created])
    ops = ShopifyOperations(client)
    request = {"blogId": blog["id"], "title": "Post", "authorName": "MOOUI", "handle": "post", "body": "<p>x</p>", "isPublished": False}
    proposal = await ops.prepare_article_create(request)
    assert proposal["article"]["author"] == {"name": "MOOUI"}
    assert (await ops.create_article({**request, "confirmationToken": proposal["confirmationToken"]}))["operation"] == "articleCreate"


def test_article_rejects_hidden_scheduled_state_and_orphan_redirect():
    with pytest.raises(ValueError, match="publishDate"):
        ShopifyOperations._validate_article_input({"isPublished": False, "publishDate": "2026-09-01T00:00:00Z"})
    with pytest.raises(ValueError, match="redirectNewHandle"):
        ShopifyOperations._validate_article_input({"redirectNewHandle": True})


@pytest.mark.asyncio
async def test_article_delete_uses_official_payload():
    article = {"id": "gid://shopify/Article/2", "title": "Post", "handle": "post", "isPublished": False, "publishedAt": None, "updatedAt": "x", "blog": {"id": "gid://shopify/Blog/1", "title": "News", "handle": "news"}}
    client = SequenceClient([{"data": {"article": article}}, {"data": {"articleDelete": {"deletedArticleId": article["id"], "userErrors": []}}}])
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_article_delete({"id": article["id"]})
    result = await ops.delete_article({"id": article["id"], "confirmationToken": proposal["confirmationToken"]})
    assert result["deletedArticleId"] == article["id"]
