# Matriz de cobertura da Shopify Admin API

Esta matriz mede cobertura operacional, não quantidade bruta de campos GraphQL. Atualize-a junto com cada nova tool. Estados: `pronto`, `parcial`, `planejado` e `não iniciado`.

| Domínio | Leitura | Escrita | Bulk/eventos | Estado |
|---|---|---|---|---|
| Loja e configuração | contexto ampliado, tipos e fornecedores | — | — | parcial |
| Access scopes | scopes concedidos | — | — | pronto |
| Produtos | lista, detalhe, handle e contagem | criação, campos básicos, tags e SEO | — | parcial |
| Variantes e opções | lista global, detalhe, busca segura por SKU | variantes em lote; opções criar, alterar, excluir e reordenar | — | pronto |
| Coleções | lista, detalhe, handle, produtos e condições de regras | criar, atualizar, excluir e membership pelo produto | — | parcial |
| Inventário e locais | itens, níveis e locais, inclusive inativos | delta com CAS/idempotência e ativação de níveis | — | pronto |
| Clientes | lista, detalhe paginado, endereços, consentimentos e contagem | tags universais | — | parcial |
| Pedidos | lista, detalhe ampliado, contagem, financeiro e riscos | nota, PO, tags, atributos e cancelamento integral | jobs assíncronos no cancelamento | parcial |
| Fulfillment | fulfillment orders, itens, ações e rastreio | criar atendimento explícito e atualizar rastreio | — | parcial |
| Returns e refunds | financeiro, motivos, devoluções e itens elegíveis | cria return moderna e refund idempotente calculado pela Shopify | — | parcial |
| Draft orders | lista e detalhe | cálculo/criação, invoice, conclusão e exclusão | — | parcial |
| Descontos e cupons | lista polimórfica, detalhe e busca por código | desconto básico com público/alvo/requisitos; ativar, desativar e excluir | — | parcial |
| Metafields | valor por owner/namespace/key e definições por owner type | set atômico com CAS, delete revalidado e CRUD de definições | — | pronto |
| Metaobjects | definições, busca por type, instâncias, handle e campos | criação de definição; CRUD de instâncias com validação de schema | — | parcial |
| Arquivos e mídia | biblioteca polimórfica, detalhe, status e erros | staged upload, criação, update, referências de produto e delete | processamento assíncrono | pronto |
| Publicações e canais | lista, detalhe e disponibilidade por recurso/canal | publicar, agendar e despublicar | — | pronto |
| Markets e preços contextuais | mercados, regiões, catálogos, price lists e preços | lifecycle de Markets e preços fixos por variante | — | pronto |
| Conteúdo, páginas e blogs | páginas, blogs e artigos com HTML e publicação | CRUD completo, agendamento, autor, tags e redirects de handle | — | pronto |
| Menus e redirects | menus hierárquicos e redirects | CRUD completo de menus e redirects | — | pronto |
| Webhooks | subscriptions shop-scoped, filtros, payload e API version | CRUD completo com endpoint validado | eventos push, HMAC/idempotência documentados | pronto |
| Bulk Operations | lista moderna, detalhe, progresso e URLs temporárias | exportação curada e cancelamento confirmado | JSONL assíncrono para 7 domínios, até 5 jobs por tipo | parcial |

## Baseline 1.17

- 74 tools de leitura no perfil padrão.
- 218 tools no total implementadas (73 leituras gerais, 72 preparações e 73 aplicações).
- Tags e SEO usam preview before/after, token assinado, expiração e proteção contra replay/adulteração.
- Criação e atualização geral de produto seguem o mesmo fluxo forte; variantes e publicação permanecem separadas.
- Variants bulk valida ownership, IDs duplicados, mudanças vazias e usa `allowPartialUpdates=false`.
- Preços entram como strings decimais para evitar perda binária de precisão.
- Estoque usa compare-and-swap obrigatório, chave de idempotência Shopify e preview por item/local.
- Exclusões irreversíveis são anotadas como destrutivas no protocolo MCP.
- Pedidos incluem financeiro, riscos, cancelamento, fulfillment explícito, rastreio, return e refund.
- Refund usa `suggestedRefund`, `allowOverRefunding=false`, transações calculadas e idempotência nativa da Shopify.
- Return usa motivos padronizados modernos e valida quantidade contra `returnableFulfillments`.
- Draft order é calculado pela Shopify antes da criação; invoice usa preview renderizado antes do envio.
- Conclusão do draft é financeira/destrutiva, verifica status e disponibilidade e reserva estoque.
- Desconto básico valida código único, GIDs de público/alvo, vigência, valor, mínimo e combinações.
- Ativação e desativação alertam sobre ajustes automáticos da Shopify em `startsAt` e `endsAt`.
- Páginas suportam HTML, agendamento/publicação, template, mudança de handle com redirect e exclusão.
- Redirects validam caminho local, destino HTTPS/local, conflito e loop direto.
- Menus validam três níveis, tipos, GIDs, handles e substituição integral da ordem.
- Menus padrão têm proteção local contra mudança de handle e exclusão.
- Blogs protegem handles e exigem política explícita ao excluir com artigos existentes.
- Artigos suportam autor, blog, HTML, resumo, tags, imagem HTTPS, publicação e redirect de handle.
- Metafields usam `compareDigest` obrigatório; `null` significa criação somente se ainda não existir.
- Delete de metafield revalida o digest após consumir o token e imediatamente antes da mutation.
- Definições suportam leitura e CRUD, validações e política explícita para apagar valores associados.
- Metaobjects validam keys conhecidas, campos obrigatórios, handles duplicados e publicação antes da confirmação.
- Definições de metaobjects validam unicidade de fields e a referência de `displayNameKey`.
- Definições de metaobjects suportam operações estruturais create/update/delete de fields e exclusão em cascata explicitamente confirmada.
- Files cobre imagens, vídeos, modelos 3D, vídeos externos e arquivos genéricos com status/erros assíncronos.
- Staged upload retorna credenciais temporárias, mas o MCP nunca lê caminhos locais nem transporta bytes.
- Atualização valida referências de produto; delete exige confirmação explícita para remover associações.
- Publicação é independente do CRUD, valida suporte a agendamento e alerta quando produto não está ACTIVE.
- Markets usa `status` moderno, condições regionais, moedas e catálogos; conflitos são validados antes da mutation.
- Catálogos ligam contexto, publicação e price list; preços fixos validam moeda e variantes antes do lote.
- Remover preço fixo mostra o fallback para o ajuste padrão da price list.
- Webhook HTTPS bloqueia hosts locais/privados e credenciais na URI; Pub/Sub e EventBridge usam formatos explícitos.
- O consumidor deve validar HMAC sobre corpo bruto, deduplicar Event ID, responder rápido e tolerar retry/ordem variável.
- Bulk exporta sete domínios por documentos internos fixos; nenhuma tool aceita GraphQL arbitrário do chamador.
- Jobs usam `bulkOperations`/`bulkOperation`, JSONL temporário e cancelamento em duas fases; o MCP não baixa nem persiste arquivos.
- Pedidos e clientes incluem alerta explícito de PII/LGPD; `groupObjects` é opt-in por impacto em timeout.
- Bulk import oferece staged upload restrito a JSONL e cinco mutations internas conhecidas; path, hash e quantidade declarada ficam vinculados ao token.
- O MCP nunca lê o arquivo: o produtor deve validar o JSONL, conferir o SHA-256 declarado e reconciliar o resultado linha a linha.
- Views compostas cobrem produto 360, pedido 360, baixo estoque e auditoria de qualidade cadastral/SEO.
- Baseline local concluída; próxima etapa externa é smoke test por domínio em development store com scopes reais.
