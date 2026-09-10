# Changelog

## Não lançado

### Adicionado
- **Composição de bundle (Shopify Bundles nativo):** os reads de produto/variante
  (`get_product`, `get_product_by_handle`, `get_product_360`, `get_product_variant`,
  `get_product_variant_by_sku`) agora trazem `requiresComponents` e
  `productVariantComponents` (variantes-peça + quantidade, com SKU/estampa). `list_products` e
  `list_product_variants` trazem o flag `requiresComponents` para detectar bundles em lote.
  Fecha a lacuna de "quais SKUs compõem um bundle".
- **Composição de bundle em RASCUNHO:** `get_draft_order`, `prepare_draft_order_create`
  (DraftOrderCalculate) e `prepare_draft_order_complete` agora pedem os componentes do kit.
  **Schema 2026-07 confirmado por introspection:** o campo é `components` (aninhado, do MESMO
  tipo do line item — traz `sku`/`quantity`/`variant`), **não** `bundleComponents`; e **não existe**
  `flattenComponents` em `draftOrder`/`calculatedDraftOrder` (só `first/after/last/before/reverse`),
  então usa-se o campo aninhado. `requiresComponents` vive em `ProductVariant`. Antes, a linha do kit
  no rascunho vinha sem SKU e os componentes sumiam do preview.
- **`shopify_shopifyql_query`:** tool de leitura que executa ShopifyQL (datasets de analytics,
  ex.: `sales` com `line_item_is_bundle`/`bundle_title`) e retorna tabela (colunas + linhas) ou
  erros de parse. Requer scope de relatórios.
- **Bulk export de produtos com componentes:** a query curada `PRODUCTS` do `start_bulk_export`
  agora inclui `requiresComponents` e `productVariantComponents` por variante, permitindo mapear
  todos os bundles do catálogo (qualquer tipo) num único JSONL.

- **Bulk import de variantes:** novo kind `PRODUCT_VARIANTS_BULK_UPDATE`
  (`productVariantsBulkUpdate` com `allowPartialUpdates:false`, uma linha JSONL por produto).
  Permite corrigir variantes de muitos produtos num único job em vez de N chamadas prepare/apply.
- **Bulk import no perfil `catalog`:** os quatro tools de importação (staged upload + import)
  saíram de `full`-somente para `catalog`+`full`, alinhados com o export.

### Corrigido
- **Bulk export/import quebrado no 2026-07:** `_BULK_OPERATION_FIELDS` selecionava
  `clientIdentifier`, que não existe no type `BulkOperation` (é argumento de
  `bulkOperationRunMutation`). Toda operação Bulk falhava com `undefinedField`. Campo removido.
- **`shopifyql_query`:** schema corrigido — `parseErrors` é escalar `String` e não há
  `TableResponse`/`PolarisVizResponse` no 2026-07; query simplificada.

- **Export de pedidos para BI:** a query curada `ORDERS` do bulk agora traz
  subtotal/frete/desconto/total, `discountCodes`, `customAttributes` e o detalhe de desconto por
  alocação (`discountAllocations` → cupom vs desconto automático/PIX), sem PII (removidos
  email/telefone/customer). `get_order` também passou a expor `discountApplications`.

### Segurança
- `prepare_bulk_export`/`start_bulk_export` disponíveis no perfil `catalog`. Export de **`ORDERS`**
  liberado no `catalog` (query sem PII); **`CUSTOMERS`** segue restrito ao perfil `full`.

### Notas
- Total de tools: **221** (74 leituras, 73 preparações, 74 aplicações).
- Exige **reiniciar o cliente MCP** para os servidores recarregarem o código.

## 1.18.0 — 2026-07-31

### Adicionado
- **Tools de peso do item de estoque:** `shopify_prepare_inventory_item_weight_update` →
  `shopify_inventory_item_weight_update` (`inventoryItemId` + `weight{value,unit}`, via
  `inventoryItemUpdate` `measurement.weight`). Fecha a lacuna de peso do fluxo de lançamento.

### Corrigido
- **`get_product_360`:** a query fechava `pageInfo` fora de `variants` e tinha um `}` sobrando,
  causando `PARSE_ERROR` da Shopify. `pageInfo` agora está dentro de `variants` (como o handler lê).
- **`productCreate`/`productUpdate` (incl. os 2 mutations de Bulk):** removido `code` de
  `userErrors{...}` — o tipo `UserError` dessas mutations não possui `code`, o que fazia a Shopify
  rejeitar a query (`undefinedField`). Demais mutations mantêm `code` (seus tipos o expõem).

### Verificado ao vivo (loja real, 2026-07-31)
- Fluxo prepare→apply com `confirmationToken` de uso único (add/remove de tag net-zero).
- Rename de opção via `product_option_update` com `variantStrategy: LEAVE_AS_IS` **não** quebra
  variantes — dispensa o REST usado em abordagens legadas.
- Atualização de SEO e lançamento completo de produto (vendor, productType, categoria, SEO, tags).

### Notas
- Total de tools: **220** (73 leituras, 73 preparações, 74 aplicações).
- Após editar `operations.py`/`catalog.py`, é preciso **reiniciar o cliente MCP** para os servidores
  recarregarem o código.
- A suíte de testes mocka as respostas GraphQL; considere um teste que valide a sintaxe/campos das
  queries para pegar erros de query sem acessar a loja.
