# Política de segurança

## Estado padrão

O servidor falha de forma fechada:

- perfil padrão `readonly`;
- escritas desabilitadas;
- mutações ausentes de `tools/list`;
- domínio restrito a `*.myshopify.com`;
- TLS verificado pelo `httpx`;
- parâmetros adicionais rejeitados;
- GIDs validados por tipo quando a tool exige um tipo específico.

## Habilitação de escrita

São necessárias cinco camadas:

1. Token com o scope Shopify correspondente.
2. `SHOPIFY_TOOL_PROFILE` que contenha a mutação.
3. `SHOPIFY_ENABLE_WRITES=true`.
4. Preview gerado por uma tool `prepare`, seguido de confirmação explícita do usuário.
5. `confirmationToken` opaco, assinado, de uso único, com validade padrão de 10 minutos e ligado exatamente à tool e aos argumentos preparados.

Quando escritas estão habilitadas, `SHOPIFY_AUDIT_LOG` é obrigatório. O log registra horário, tool, resultado, nomes dos campos, contagens e hash do alvo. Não registra token, GID original, tags, conteúdo SEO ou valores de negócio.

Alterar qualquer argumento depois do preview invalida o token. Tokens expiram, não sobrevivem ao reinício do processo e são consumidos antes da mutação para impedir replay; quando uma chamada falha, uma nova preparação é necessária.

## Dados sensíveis

Pedidos e clientes contêm PII. O servidor não grava respostas em cache ou log. O host MCP é responsável por controle de acesso, retenção e pelo destino do conteúdo apresentado ao modelo. Novas tools devem selecionar apenas os campos necessários e documentar quando retornam PII.

Fulfillments exigem itens e quantidades explícitos; o MCP não oferece o atalho de atender implicitamente todos os itens. A preparação valida ownership, pedido, local, ação suportada e quantidade restante. Notificações ao cliente são booleanos obrigatórios, aparecem no preview e fazem parte do token de confirmação.

Cancelamento de pedido é classificado como financeiro, destrutivo e irreversível. Refund ao meio original, restock, motivo, nota interna e notificação são obrigatoriamente explícitos e vinculados ao token. A preparação rejeita pedidos já cancelados e pedidos com devoluções ativas.

## Regras para novas mutações

- Declarar se é idempotente, reversível, destrutiva ou financeira.
- Nunca repetir automaticamente uma mutação não idempotente após timeout/5xx.
- Separar cálculo/preview da execução para cancelamentos, refunds, inventário absoluto e lotes.
- Validar ownership de recursos filhos antes de mutações em lote (por exemplo, variante → produto).
- Valores monetários entram como strings decimais; floats JSON não são aceitos.
- Usar compare-and-set quando a API oferecer controle de concorrência.
- Em `metafieldsSet`, exigir `compareDigest` mesmo sendo opcional na API: digest atual para update e `null` para create-only.
- Como `metafieldsDelete` não oferece CAS nativo, reler e comparar o digest imediatamente antes da exclusão.
- Metaobjects devem ser validados contra a definição atual; keys desconhecidas e campos obrigatórios ausentes são rejeitados antes de emitir confirmação.
- Mudanças de handle exigem política explícita de redirect; exclusão alerta que referências externas podem perder o destino.
- Remover fields de metaobject exige `acknowledgeFieldDataLoss=true`; apagar a definição exige `confirmCascade=true` porque a Shopify remove instâncias e metafields relacionados.
- Staged uploads recebem somente filename, MIME type e tamanho; caminhos locais e bytes não fazem parte de nenhuma tool.
- Targets de upload contêm credenciais temporárias e não são persistidos em log; delete de Files exige reconhecimento da remoção de referências.
- Publicação/despublicação é sempre separada do CRUD; cada canal, agendamento e estado anterior aparece no preview e no token.
- Ativar Market ou alterar condições pode mudar imediatamente o contexto do comprador; a preparação destaca esse impacto e valida catálogos referenciados.
- Preços contextuais aceitam apenas strings decimais, exigem a moeda da price list e mostram o valor fixo anterior antes de substituir ou remover.
- Webhook HTTPS rejeita localhost, sufixos internos, IPs não globais e userinfo. O consumidor deve validar `X-Shopify-Hmac-Sha256` no corpo bruto com comparação constante.
- Eventos precisam de deduplicação por `X-Shopify-Event-Id`, processamento assíncrono, tolerância a retries e entrega fora de ordem.
- Mutations não são repetidas automaticamente após timeout ou HTTP 5xx: o resultado é marcado como desconhecido e deve ser reconciliado antes de nova preparação.
- Confirmações pendentes são limitadas e propostas expiradas são removidas para evitar crescimento ilimitado de memória.
- Bulk query/import aceita somente documentos internos conhecidos. Hash e contagem do JSONL são declarações vinculadas ao token; como o MCP não lê bytes, o pipeline produtor deve verificá-los.
- Limitar arrays a no máximo 250 e adotar limite operacional menor quando o risco justificar.
- Tratar `userErrors` como falha, mesmo com HTTP 200.
- Registrar auditoria tanto no sucesso quanto na falha, sem payload sensível.

## Segredos

O token é recebido apenas pelo ambiente do processo e nunca por argumento de tool. O projeto não carrega `.env` automaticamente nem importa credenciais dos projetos históricos. Mensagens HTTP são redigidas antes de serem incluídas em detalhes de erro.

## Transporte remoto

Esta fase suporta apenas `stdio` local. Streamable HTTP só será habilitado com autenticação, HTTPS, validação de `Origin`, isolamento por loja, limites de requisição e revisão específica do modelo de ameaça.
