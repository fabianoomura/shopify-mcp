# Changelog

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
