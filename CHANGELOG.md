# Changelog

## Não lançado

### Corrigido
- **Coleções automáticas na API 2026-07:** `ruleSet` saiu de `CollectionCreateInput`/`CollectionUpdateInput`
  (a Shopify recusava com "Field is not defined"). As tools de coleção continuam aceitando `ruleSet` no formato
  clássico e o MCP converte para uma **fonte de condições** (`sources`/`sourcesToCreate`): TAG → `productTag`
  `TAGGED_WITH`/`NOT_TAGGED_WITH`, NOT_CONTAINS → `DOES_NOT_CONTAIN`, `appliedDisjunctively` → `matchType` ANY/ALL,
  preço em `MoneyInput` BRL. Na atualização, a fonte de condições atual é apagada e recriada; a fonte só de
  seleções manuais é preservada e o MCP recusa apagar fonte que mistura condições e seleções.
  Saíram `IS_PRICE_REDUCED` (use `VARIANT_COMPARE_AT_PRICE IS_SET`) e `PRODUCT_TAXONOMY_NODE_ID`.
  Condições negativas (`NOT_EQUALS`, `NOT_CONTAINS`, tag negada) vão com `matchType: ALL` — a Shopify
  recusa ANY nelas ("Match type must be ALL when relation is not_contains").
- **Cupons (`list_code_discounts`, `get_code_discount`, `get_code_discount_by_code`):** o fragmento tinha uma
  `}` sobrando e a Shopify devolvia `PARSE_ERROR`. Teste novo confere o balanço das chaves.
- **`list_price_lists`:** `priceLists` não aceita `query` no 2026-07 (`argumentNotAccepted`); o argumento foi retirado.
- **Menus com 3 níveis:** o validador contava a lista `items: []` das folhas do 3º nível como um 4º nível
  e recusava todo menu de 3 níveis ("Menu aceita no máximo três níveis"). Agora só recusa se houver itens no 4º.
- **`prepare_collection_delete`:** o preview pedia `publications{nodes{id name}}`, que não existe em
  `CollectionPublication` no 2026-07 (a tool falhava sempre). Agora usa
  `resourcePublications{nodes{isPublished publication{id name}}}`.

### Adicionado
- **Descontos automáticos (Compre X Ganhe Y):** `shopify_list_automatic_discounts` e `shopify_get_automatic_discount`
  (leitura); `shopify_prepare_discount_automatic_bxgy_create` → `shopify_create_discount_automatic_bxgy`
  (`discountAutomaticBxgyCreate`; ex.: 3x2 = `buysQuantity:2` + `getsQuantity:1` + `getsPercentage:1`, por
  produtos ou coleções); ativar/desativar (`discountAutomaticActivate/Deactivate`) e excluir
  (`discountAutomaticDelete`) com prepare→apply. O preview resolve os GIDs (com nº de produtos da coleção) e avisa
  título repetido, `productDiscounts` desligado (promos de grupos diferentes não somam no carrinho) e repetição
  sem `usesPerOrderLimit`. Pedido para o 3x2 da loja Barcelona. Validado ao vivo em 20/10/2026 (5 promos 3x2 na BCN).
- **Datas de descontos em lote:** `shopify_prepare_discount_dates_update` → `shopify_update_discount_dates`, até 100
  cupons (`DiscountCodeNode`) e/ou descontos automáticos (`DiscountAutomaticNode`) por vez, com before/after por item.
  Detecta o tipo (Basic/Bxgy/FreeShipping/App) e chama o `discount*Update` certo enviando só `startsAt`/`endsAt`.
  `endsAt` = agora desativa em lote; `endsAt: null` tira a data de fim. Falhas são reportadas por ID sem
  interromper o resto. Recusa `endsAt` anterior ao `startsAt` atual de qualquer item.
- **Alvo de cupom:** `shopify_prepare_discount_code_items_update` → `shopify_update_discount_code_items` trocam onde um
  cupom percentual/valor (`DiscountCodeBasic`) vale: todos, produtos ou coleções. O preview lê o alvo atual e
  manda só o diff (`add`/`remove`); valor, público, vigência e combinações não mudam. Recusa quando o alvo atual
  tem 20+ itens (o preview não enxergaria todos). As leituras de cupom passam a mostrar `customerGets.items`.
- **Regras por metafield de lista** (`METAFIELD_STRING_LIST`, `METAFIELD_METAOBJECT_LIST` + `definitionId`):
  ex. tema (`custom.tema`) e cor (`custom.cor`) em coleções automáticas.
- **Peso no bulk export:** `PRODUCTS` e `PRODUCT_VARIANTS` trazem `inventoryItem.measurement.weight` por variante
  (e `PRODUCT_VARIANTS` traz `productType`/`tags` do produto), para auditar peso por família e tamanho de uma vez.
- **Bulk export `COLLECTIONS` com produtos:** cada coleção traz `products{id handle status}` (linhas filhas com
  `__parentId`), para auditar membership em massa (ex.: se a coleção-mãe do menu contém todas as filhas).
- **Subcoleções em blocos de 10:** a Shopify aceita no máximo 10 coleções por fonte de subcoleções (testado:
  10 ok, 11 "Too many sub-collections"). O MCP divide `subCollectionIds` em várias fontes de até 10.
- **`subCollectionIds`** em criar/atualizar coleção: fonte de **subcoleções** — a coleção-mãe herda os produtos
  das coleções informadas (níveis de cima do menu puxando os de baixo).
- **`shopify_list_orders_attribution` (leitura, todos os perfis):** pedidos com os campos da atribuição de
  marketing — valor, estorno, status, `sourceName`/app (loja, rascunho, TikTok), `clientIp` e
  `customerJourneySummary` (primeira/última visita com UTMs, página de entrada, nº de momentos).
  Sem nome, e-mail ou telefone; resposta marcada `containsPii` por causa do IP. Pedido do agente de
  marketing (Dory, `mooui_dory`) para ligar pedidos sem evento do pixel. Testado na loja em 01/10/2026:
  pedidos web trazem IP e jornada; TikTok sem IP.
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
- **Bulk import de tags:** kinds `TAGS_ADD` e `TAGS_REMOVE` (`tagsAdd`/`tagsRemove`, uma linha por
  produto com `id` + `tags:[...]`). Aditivo por construção — nunca substitui o conjunto de tags,
  ao contrário de `productUpdate(tags)`. Para sincronizar navegação em massa sem risco de apagar tags.
- **Bulk import de publicação:** kinds `PUBLISHABLE_PUBLISH` e `PUBLISHABLE_UNPUBLISH`
  (`publishablePublish`/`publishableUnpublish`, uma linha JSONL por produto/coleção com `id` +
  `input:[{publicationId}]`). Permite (re)publicar centenas de produtos num canal num único job.
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
- Escritas de **desconto automático**, **datas de descontos** e **alvo de cupom** liberadas no `catalog` (gestão
  de promoção); criar/excluir/ativar cupom (`discount_code_*`) segue em `orders`/`full`.

### Notas
- Total de tools: **238** (77 leituras, 80 preparações, 81 aplicações).
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
