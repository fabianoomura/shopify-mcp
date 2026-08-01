import pytest

from shopify_mcp.confirmations import ConfirmationError, ConfirmationManager


def test_confirmation_is_bound_to_tool_and_exact_arguments():
    manager = ConfirmationManager(secret=b"x" * 32)
    issued = manager.issue("shopify_add_tags", {"id": "p1", "tags": ["sale"]})
    with pytest.raises(ConfirmationError, match="corresponde"):
        manager.consume(issued["confirmationToken"], "shopify_add_tags", {"id": "p1", "tags": ["other"]})


def test_confirmation_is_single_use():
    manager = ConfirmationManager(secret=b"x" * 32)
    args = {"id": "p1", "tags": ["sale"]}
    token = manager.issue("shopify_add_tags", args)["confirmationToken"]
    manager.consume(token, "shopify_add_tags", args)
    with pytest.raises(ConfirmationError, match="já utilizado"):
        manager.consume(token, "shopify_add_tags", args)


def test_tampered_confirmation_is_rejected():
    manager = ConfirmationManager(secret=b"x" * 32)
    token = manager.issue("shopify_add_tags", {})["confirmationToken"]
    with pytest.raises(ConfirmationError, match="inválido"):
        manager.consume(token + "tampered", "shopify_add_tags", {})


def test_expired_confirmation_is_rejected(monkeypatch):
    manager = ConfirmationManager(ttl_seconds=30, secret=b"x" * 32)
    token = manager.issue("shopify_add_tags", {})["confirmationToken"]
    monkeypatch.setattr("shopify_mcp.confirmations.time.time", lambda: 10**20)
    with pytest.raises(ConfirmationError, match="expirado"):
        manager.consume(token, "shopify_add_tags", {})


def test_pending_confirmation_limit_and_expiry_pruning(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("shopify_mcp.confirmations.time.time", lambda: now[0])
    manager = ConfirmationManager(ttl_seconds=30, secret=b"x" * 32, max_pending=1)
    manager.issue("one", {})
    with pytest.raises(ConfirmationError, match="Limite"):
        manager.issue("two", {})
    now[0] += 31
    manager.issue("two", {})
