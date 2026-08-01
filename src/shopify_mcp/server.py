from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

import mcp.server.stdio
import mcp.types as types
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from . import __version__
from .audit import MutationAuditor
from .catalog import enabled_definitions
from .client import ShopifyClient, ShopifyError
from .config import Settings
from .confirmations import ConfirmationManager
from .operations import ShopifyOperations

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("shopify-mcp")
server = Server("mooui-shopify-mcp")
_operations: ShopifyOperations | None = None
_settings: Settings | None = None
_auditor: MutationAuditor | None = None
_confirmations: ConfirmationManager | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def get_operations() -> ShopifyOperations:
    global _operations
    if _operations is None:
        _operations = ShopifyOperations(ShopifyClient(get_settings()), get_confirmations())
    return _operations


def get_confirmations() -> ConfirmationManager:
    global _confirmations
    if _confirmations is None:
        _confirmations = ConfirmationManager(get_settings().confirmation_ttl_seconds)
    return _confirmations


def get_auditor() -> MutationAuditor:
    global _auditor
    if _auditor is None:
        _auditor = MutationAuditor(get_settings().audit_log)
    return _auditor


def active_definitions():
    settings = get_settings()
    return enabled_definitions(settings.tool_profile, settings.enable_writes)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [definition.tool for definition in active_definitions()]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    active = {definition.tool.name: definition for definition in active_definitions()}
    definition = active.get(name)
    if not definition:
        return [types.TextContent(type="text", text=json.dumps({"error": "Tool não encontrada ou desabilitada pelo perfil", "tool": name}, ensure_ascii=False))]

    arguments = arguments or {}
    try:
        Draft202012Validator(definition.tool.inputSchema).validate(arguments)
        result = await getattr(get_operations(), definition.route)(arguments)
        if definition.write:
            get_auditor().record(tool=name, arguments=arguments, outcome="success")
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except (ShopifyError, ValidationError, ValueError, KeyError) as exc:
        if definition.write:
            get_auditor().record(tool=name, arguments=arguments, outcome="failure", error_type=type(exc).__name__)
        logger.warning("Falha em %s: %s", name, exc)
        payload = {"error": str(exc), "tool": name}
        if isinstance(exc, ShopifyError) and exc.details is not None:
            payload["details"] = exc.details
        return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]
    except Exception as exc:
        if definition.write:
            get_auditor().record(tool=name, arguments=arguments, outcome="failure", error_type=type(exc).__name__)
        logger.exception("Erro inesperado em %s", name)
        return [types.TextContent(type="text", text=json.dumps({"error": "Erro interno inesperado", "tool": name}, ensure_ascii=False))]


async def main() -> None:
    settings = get_settings()
    instructions = (
        f"Perfil ativo: {settings.tool_profile}. Escritas: {'habilitadas' if settings.enable_writes else 'desabilitadas'}. "
        "Use shopify_get_shop para validar a conexão. Leituras podem ser executadas diretamente. "
        "Antes de qualquer mutação, chame a tool prepare correspondente, mostre before/after ao usuário e use o confirmationToken após confirmação explícita. "
        "Nunca invente IDs: consulte o recurso e use seu GID. Use filtros e paginação para manter respostas pequenas."
    )
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mooui-shopify-mcp",
                server_version=__version__,
                instructions=instructions,
                capabilities=server.get_capabilities(notification_options=NotificationOptions(), experimental_capabilities={}),
            ),
        )


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
