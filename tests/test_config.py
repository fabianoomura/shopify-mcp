import pytest

from shopify_mcp.config import Settings


def test_settings_rejects_non_shopify_domain(monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP_DOMAIN", "https://evil.example/path")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "secret")
    with pytest.raises(ValueError, match="myshopify"):
        Settings.from_env()


def test_writes_are_disabled_by_default(monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP_DOMAIN", "example.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "secret")
    monkeypatch.delenv("SHOPIFY_ENABLE_WRITES", raising=False)
    assert Settings.from_env().enable_writes is False


def test_writes_require_non_readonly_profile_and_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("SHOPIFY_SHOP_DOMAIN", "example.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "secret")
    monkeypatch.setenv("SHOPIFY_ENABLE_WRITES", "true")
    monkeypatch.setenv("SHOPIFY_TOOL_PROFILE", "readonly")
    with pytest.raises(ValueError, match="perfil"):
        Settings.from_env()

    monkeypatch.setenv("SHOPIFY_TOOL_PROFILE", "catalog")
    monkeypatch.delenv("SHOPIFY_AUDIT_LOG", raising=False)
    with pytest.raises(ValueError, match="AUDIT_LOG"):
        Settings.from_env()

    monkeypatch.setenv("SHOPIFY_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    settings = Settings.from_env()
    assert settings.enable_writes is True
    assert settings.tool_profile == "catalog"


def test_invalid_tool_profile_is_rejected(monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP_DOMAIN", "example.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "secret")
    monkeypatch.setenv("SHOPIFY_TOOL_PROFILE", "everything")
    with pytest.raises(ValueError, match="TOOL_PROFILE"):
        Settings.from_env()
