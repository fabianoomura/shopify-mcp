# Arquitetura do MOOUI Shopify MCP

## Limite do sistema

Este servidor conhece exclusivamente a Shopify. Ele não chama outros sistemas externos (ERP, pagamentos, logística) nem um futuro barramento central. Um orquestrador externo pode combinar MCPs sem acoplar credenciais, disponibilidade ou modelos de dados entre eles.

```text
Host/agente MCP
      |
      v
server.py       protocolo, validação e roteamento
      |
      +-- catalog.py       schemas, risco, domínio e perfis
      +-- operations.py    operações Shopify curadas
      +-- client.py        Admin GraphQL, TLS, retry e erros
      +-- audit.py         auditoria redigida de mutações
      +-- config.py        configuração fail-closed
```

## Regras arquiteturais

1. GraphQL é interno. Não será exposta uma tool de GraphQL arbitrário, pois ela contornaria schemas, perfis e confirmações.
2. Cada tool pertence a um domínio Shopify e possui schema fechado (`additionalProperties=false`).
3. Leituras e mutações têm anotações MCP coerentes. Mutações não são anunciadas quando escritas estão desabilitadas.
4. Escritas usam `prepare`/`apply` com token opaco de uso único; operações em massa têm limites explícitos e resumo por item.
5. Paginação devolve `endCursor`; respostas grandes podem usar Bulk Operations e JSONL temporário.
6. A API é versionada explicitamente. `shopify_get_shop` informa versão solicitada e versão efetivamente servida.
7. O catálogo é classificado por módulos; perfis evitam apresentar escritas irrelevantes ao agente.

## Perfis

- `readonly`: somente consultas; perfil padrão.
- `catalog`: consultas gerais e escritas de catálogo.
- `orders`: consultas gerais e operações de pedido/fulfillment.
- `full`: todos os módulos autorizados.

O perfil seleciona o catálogo. `SHOPIFY_ENABLE_WRITES` funciona como segundo bloqueio independente. Scopes do token Shopify formam o terceiro bloqueio.

## Evolução dos módulos

O catálogo cresce por fatias verticais: schema, operação, testes unitários, teste de contrato, documentação e atualização da matriz de cobertura na mesma mudança. A baseline atual já cobre loja/acessos, produtos/variantes, coleções, inventário, clientes, pedidos/fulfillment, descontos, conteúdo, metafields/metaobjects, arquivos/publicações, mercados, bulk e webhooks.
