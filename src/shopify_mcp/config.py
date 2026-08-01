from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$", re.IGNORECASE)
VERSION_RE = re.compile(r"^20\d{2}-(01|04|07|10)$")


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "sim"}


@dataclass(frozen=True, slots=True)
class Settings:
    domain: str
    access_token: str
    api_version: str = "2026-07"
    enable_writes: bool = False
    timeout_seconds: float = 30.0
    max_retries: int = 3
    tool_profile: str = "readonly"
    audit_log: Path | None = None
    confirmation_ttl_seconds: int = 600

    @classmethod
    def from_env(cls) -> "Settings":
        domain = os.getenv("SHOPIFY_SHOP_DOMAIN", "").strip().lower()
        token = os.getenv("SHOPIFY_ACCESS_TOKEN", "").strip()
        version = os.getenv("SHOPIFY_API_VERSION", "2026-07").strip()
        if not DOMAIN_RE.fullmatch(domain):
            raise ValueError("SHOPIFY_SHOP_DOMAIN deve ser como nome-da-loja.myshopify.com")
        if not token:
            raise ValueError("SHOPIFY_ACCESS_TOKEN não configurado")
        if not VERSION_RE.fullmatch(version):
            raise ValueError("SHOPIFY_API_VERSION deve usar YYYY-01, YYYY-04, YYYY-07 ou YYYY-10")
        enable_writes = truthy(os.getenv("SHOPIFY_ENABLE_WRITES"))
        profile = os.getenv("SHOPIFY_TOOL_PROFILE", "readonly").strip().lower()
        if profile not in {"readonly", "catalog", "orders", "full"}:
            raise ValueError("SHOPIFY_TOOL_PROFILE deve ser readonly, catalog, orders ou full")
        audit_value = os.getenv("SHOPIFY_AUDIT_LOG", "").strip()
        audit_log = Path(audit_value).expanduser().resolve() if audit_value else None
        confirmation_ttl = int(os.getenv("SHOPIFY_CONFIRMATION_TTL_SECONDS", "600"))
        if not 30 <= confirmation_ttl <= 3600:
            raise ValueError("SHOPIFY_CONFIRMATION_TTL_SECONDS deve estar entre 30 e 3600")
        if enable_writes and profile == "readonly":
            raise ValueError("SHOPIFY_ENABLE_WRITES=true exige um perfil diferente de readonly")
        if enable_writes and audit_log is None:
            raise ValueError("SHOPIFY_AUDIT_LOG é obrigatório quando escritas estão habilitadas")
        timeout_seconds = float(os.getenv("SHOPIFY_TIMEOUT_SECONDS", "30"))
        max_retries = int(os.getenv("SHOPIFY_MAX_RETRIES", "3"))
        if not 0.1 <= timeout_seconds <= 120:
            raise ValueError("SHOPIFY_TIMEOUT_SECONDS deve estar entre 0.1 e 120")
        if not 0 <= max_retries <= 10:
            raise ValueError("SHOPIFY_MAX_RETRIES deve estar entre 0 e 10")
        return cls(
            domain=domain,
            access_token=token,
            api_version=version,
            enable_writes=enable_writes,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            tool_profile=profile,
            audit_log=audit_log,
            confirmation_ttl_seconds=confirmation_ttl,
        )
