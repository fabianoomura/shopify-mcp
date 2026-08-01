from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from . import __version__
from .config import Settings

logger = logging.getLogger("shopify-mcp.client")


class ShopifyError(RuntimeError):
    """Erro HTTP, GraphQL ou de validação retornado pela Shopify."""

    def __init__(self, message: str, *, status_code: int | None = None, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class ShopifyClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.url = f"https://{settings.domain}/admin/api/{settings.api_version}/graphql.json"
        self._http = httpx.AsyncClient(
            timeout=settings.timeout_seconds,
            transport=transport,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": settings.access_token,
                "User-Agent": f"mooui-shopify-mcp/{__version__}",
            },
        )

    def _safe_text(self, value: str, limit: int = 2000) -> str:
        return value.replace(self.settings.access_token, "[REDACTED]")[:limit]

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        retries_left = self.settings.max_retries
        # A mutation pode ter sido aplicada mesmo quando a conexão cai ou um proxy
        # devolve 5xx. Repeti-la automaticamente criaria duplicatas ou efeitos duplos.
        is_mutation = query.lstrip().startswith("mutation")
        while True:
            try:
                response = await self._http.post(self.url, json={"query": query, "variables": variables or {}})
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if retries_left <= 0 or is_mutation:
                    message = "Resultado da mutation é desconhecido após falha de rede; reconcilie o estado antes de tentar novamente" if is_mutation else "Falha de rede ao acessar a Shopify"
                    raise ShopifyError(message, details={"errorType": type(exc).__name__, "outcomeUnknown": is_mutation}) from exc
                retries_left -= 1
                await asyncio.sleep(2 ** (self.settings.max_retries - retries_left - 1))
                continue

            if response.status_code == 429 or (response.status_code >= 500 and not is_mutation):
                if retries_left > 0:
                    retries_left -= 1
                    wait = float(response.headers.get("Retry-After", "1"))
                    await asyncio.sleep(max(wait, 0.1))
                    continue

            if response.status_code >= 500 and is_mutation:
                raise ShopifyError(
                    "Resultado da mutation é desconhecido após erro 5xx; reconcilie o estado antes de tentar novamente",
                    status_code=response.status_code,
                    details={"requestId": response.headers.get("X-Request-ID"), "outcomeUnknown": True},
                )

            if response.status_code >= 400:
                request_id = response.headers.get("X-Request-ID")
                raise ShopifyError(
                    f"Shopify respondeu HTTP {response.status_code}",
                    status_code=response.status_code,
                    details={"body": self._safe_text(response.text), "requestId": request_id},
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise ShopifyError("Shopify retornou JSON inválido", details=self._safe_text(response.text, 1000)) from exc

            errors = payload.get("errors") or []
            throttled = any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in errors)
            if throttled and retries_left > 0:
                retries_left -= 1
                status = ((payload.get("extensions") or {}).get("cost") or {}).get("throttleStatus") or {}
                available = float(status.get("currentlyAvailable", 0))
                restore = max(float(status.get("restoreRate", 50)), 1.0)
                await asyncio.sleep(max(1.0, (1.0 - available) / restore))
                continue
            if errors:
                raise ShopifyError("Erro GraphQL da Shopify", details=errors)

            data = payload.get("data")
            if data is None:
                raise ShopifyError("Resposta GraphQL sem campo data", details=payload)
            return {
                "data": data,
                "extensions": payload.get("extensions", {}),
                "meta": {
                    "requestedApiVersion": self.settings.api_version,
                    "servedApiVersion": response.headers.get("X-Shopify-API-Version"),
                    "requestId": response.headers.get("X-Request-ID"),
                },
            }

    async def close(self) -> None:
        await self._http.aclose()


def mutation_result(payload: dict[str, Any], field: str) -> dict[str, Any]:
    result = payload["data"].get(field) or {}
    user_errors = result.get("userErrors") or []
    if user_errors:
        raise ShopifyError(f"Shopify rejeitou a operação {field}", details=user_errors)
    return result
