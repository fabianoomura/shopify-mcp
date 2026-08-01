# Análise de lacunas — Shopify MCP

Auditoria atualizada em 2026-07-21 para a versão 1.17.0.

## Escopo concluído

O servidor local de loja única é um MCP operacional e isolado. Ele implementa `stdio`, handshake, descoberta e chamada de tools, JSON Schemas fechados, perfis, Admin GraphQL 2026-07, paginação, Bulk Operations, webhooks e fluxo `prepare/apply` para escritas. Não lê credenciais, bancos ou arquivos de outros MCPs ou sistemas externos.

Scripts históricos de projetos legados foram usados apenas para levantar necessidades. Não foram publicados diretamente porque combinavam REST legado, versões antigas, execução interativa, arquivos locais e controles de segurança insuficientes.

Cobertura funcional detalhada: [API_COVERAGE.md](API_COVERAGE.md). As limitações marcadas como `parcial` indicam que a Shopify possui operações especializadas adicionais, não que o domínio esteja ausente.

## Critérios locais atendidos

- pacote instalável e entrypoint `shopify-mcp`;
- 218 tools curadas: 73 leituras, 72 preparações e 73 aplicações;
- nenhuma tool de GraphQL arbitrário;
- 161 testes automatizados, build de sdist/wheel e teste real de handshake `stdio`;
- TLS verificado, domínio `*.myshopify.com`, token somente no ambiente e erros redigidos;
- mutations não são repetidas após timeout ou 5xx com resultado ambíguo;
- auditoria sem valores de negócio/PII e confirmações assinadas, exatas, expirantes e de uso único;
- exports/imports Bulk com documentos internos conhecidos; arquivos e bytes permanecem fora do processo MCP;
- views compostas para produto, pedido, baixo estoque e qualidade cadastral.

## Validação externa ainda necessária

Estas ações dependem de uma loja e credenciais e, portanto, não podem ser concluídas apenas no repositório:

1. Instalar um app custom/development com os scopes realmente necessários.
2. Executar `shopify_get_shop` e `shopify_get_access_scopes` com perfil `readonly`.
3. Fazer smoke tests de cada domínio usado pela loja em uma development store.
4. Só então habilitar escritas, inicialmente por perfil, usando dados descartáveis e revisando o audit log.
5. Registrar quais recursos exigem Shopify Plus, aprovação protegida ou scopes opcionais, conforme o plano da loja.

Sem esse smoke test, o código está verificado contra contratos e mocks, mas não se deve afirmar que todas as permissões e recursos estão disponíveis na loja.

## Fora do limite deste servidor

OAuth multi-tenant, Streamable HTTP público, armazenamento central de tokens, fila consumidora de webhooks, observabilidade distribuída e um banco central de plataforma pertencem à futura plataforma/orquestrador. Adicioná-los aqui quebraria o limite “Shopify apenas” e o modelo local de loja única.

## Evolução possível sem bloquear o uso atual

- mutations especializadas de discounts (BXGY, frete grátis e app functions);
- exchanges, disputes, subscriptions, B2B companies e selling plans, caso entrem no negócio;
- Resources/prompts MCP para manuais não sensíveis;
- Tasks MCP quando SDK e hosts adotados estabilizarem o recurso.

Esses itens devem entrar por necessidade concreta, sempre em fatia vertical com schema, preview, aplicação, testes e documentação.
