# MOOUI Shopify MCP

Servidor MCP para a Shopify Admin GraphQL API. O projeto nasce isolado: nenhum `.env`, token, planilha, cache ou banco de projetos legados foi copiado.

## O que já é MCP de verdade

- handshake MCP e transporte `stdio`;
- descoberta e chamada de tools com JSON Schema;
- anotações de leitura/escrita para clientes MCP;
- cliente assíncrono GraphQL, TLS verificado e domínio restrito a `*.myshopify.com`;
- API versionada (`2026-07` por padrão), paginação por cursor e respostas compactas;
- tratamento de HTTP, erros GraphQL, `userErrors`, throttling e retry;
- escritas desligadas por padrão e confirmação dupla;
- testes sem acessar a loja real e pacote instalável com comando `shopify-mcp`.

## Cobertura atual

A versão atual oferece 221 tools curadas: 74 leituras, 73 preparações e 74 aplicações. Cobre loja/scopes, produtos, variantes/opções, coleções, inventário/locais (incl. peso de itens de estoque), clientes, pedidos, fulfillment, returns/refunds, draft orders, descontos, páginas/blogs/artigos, menus/redirects, metafields/metaobjects, arquivos/mídia, publicações, Markets/catálogos/price lists, webhooks e Bulk Operations.

Views compostas entregam produto 360, pedido 360, baixo estoque e auditoria de qualidade cadastral/SEO. Bulk exporta sete domínios e importa cinco tipos de mutation conhecidos sem expor GraphQL arbitrário.

Cada aplicação exige o `confirmationToken` retornado pela preparação correspondente; o token é de uso único, ligado exatamente aos argumentos e expira. Criações não publicam automaticamente. Mutations não são repetidas após falha ambígua de rede/5xx.

No perfil padrão `readonly`, apenas as tools de leitura são anunciadas. Consulte [Arquitetura](docs/ARCHITECTURE.md), [Segurança](docs/SECURITY.md) e [Cobertura da API](docs/API_COVERAGE.md).

## Instalação

```powershell
cd C:\projetos\mcp-servers\shopify-mcp
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Use `.env.example` apenas como referência. O servidor lê variáveis do processo; ele não carrega `.env` automaticamente. Isso evita escolher silenciosamente um arquivo de credenciais errado. Configure no cliente MCP:

```json
{
  "mcpServers": {
    "shopify": {
      "command": "C:\\projetos\\mcp-servers\\shopify-mcp\\.venv\\Scripts\\shopify-mcp.exe",
      "env": {
        "SHOPIFY_SHOP_DOMAIN": "sua-loja.myshopify.com",
        "SHOPIFY_ACCESS_TOKEN": "SEU_TOKEN",
        "SHOPIFY_API_VERSION": "2026-07",
        "SHOPIFY_TOOL_PROFILE": "readonly",
        "SHOPIFY_ENABLE_WRITES": "false"
      }
    }
  }
}
```

Para validar:

```powershell
.\.venv\Scripts\python -m pytest
```

## Escopos Shopify

Comece com mínimo privilégio e confirme os scopes efetivos com `shopify_get_access_scopes`. Uma base de leitura comum inclui `read_products`, `read_inventory`, `read_orders`, `read_customers` e `read_locations`; cada domínio adicional exige seus scopes correspondentes. Para escritas de catálogo/estoque, acrescente apenas os scopes necessários, use `SHOPIFY_TOOL_PROFILE=catalog`, configure `SHOPIFY_AUDIT_LOG` e altere `SHOPIFY_ENABLE_WRITES=true`. Pedidos anteriores a 60 dias exigem `read_all_orders`, sujeito à aprovação da Shopify.

## Estado e próximo passo

A baseline local de loja única está concluída: suíte automatizada, pacote e handshake MCP real passam. O próximo passo obrigatório é um smoke test somente leitura em uma development store e, depois, testes de escrita com dados descartáveis. OAuth multi-loja, Streamable HTTP público, fila consumidora e um banco central de plataforma ficam fora deste servidor isolado. Veja [Análise de lacunas](docs/GAP_ANALYSIS.md).
