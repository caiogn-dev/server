# server2 - Contratos Criticos

Data: 2026-04-24
Fonte geral: `/home/graco/WORK/PASTITA_ESTADO_PLANEJAMENTO_2026-04-24.md`

## Objetivo

Registrar os contratos que os frontends e automacoes nao podem quebrar sem migracao coordenada.

## Auth

### Dashboard/Admin

- Header: `Authorization: Token <token>`
- Nao assumir JWT como padrao do `server2`.
- Clientes admin devem lidar com `401` limpando token local e redirecionando para login.

### WhatsApp OTP Mobile

Endpoints:

- `POST /api/v1/auth/whatsapp/send/`
- `POST /api/v1/auth/whatsapp/verify/`
- `POST /api/v1/auth/whatsapp/resend/`

Template Meta:

- `codigo_verificacao`

Regras:

- OTP deve sair por template, nao texto livre, para funcionar fora da janela de 24h.
- O template exige parametro no `body` e no botao URL/copy-code.
- Resposta de verify retorna `token` DRF e usuario.
- App mobile deve salvar token e enviar `Authorization: Token <token>`.

Identidade:

- Usuario criado apenas por telefone pode ter email tecnico `{phone}@pastita.local`.
- Esse email e interno, nao deve aparecer como nome/email real no app.
- Nomes placeholder (`cliente_...`, `desconhecido`, `@pastita.local`) devem ser filtrados na API/UI.

## Storefront Publico

Catalogo:

- `GET /api/v1/public/{slug}/catalog/`
- `slug` principal atual do mobile: `ce-saladas`
- Categorias de ingredientes podem existir no catalogo, mas o app mobile deve exibir ingredientes so no fluxo `Monte sua salada`.

Disponibilidade:

- `GET /api/v1/public/{slug}/availability/`
- Sem auth.

## Carrinho Web

Headers/params:

- `X-Cart-Key`
- `cart_key`

Regras:

- Carrinho anonimo deve continuar funcionando para `ce-saladas` e `pastita-3d`.
- Guest checkout e requisito de storefront web.

## Checkout

Endpoint web historico:

- `POST /api/v1/stores/{slug}/checkout/`

Regras:

- Deve aceitar guest quando aplicavel.
- Deve receber dados de cliente, endereco, metodo de entrega, metodo de pagamento e itens.
- Proximo trabalho: confirmar/estender payload para `ce-saladas-flutter`, incluindo salada personalizada.

Contrato pendente para mobile:

- produto normal: id, quantidade, preco vigente
- salada personalizada: nome escolhido, ingredientes selecionados, preco calculado, observacoes
- endereco: endereco selecionado/autosuggest/GPS normalizado
- pagamento: pix/cartao/dinheiro conforme tela
- retorno: order id, order number/token, status, total e dados para tela de sucesso/pendente/erro

## Perfil e Enderecos

Perfil cliente:

- `GET/PATCH /api/v1/stores/{slug}/customer/profile/`

Regras:

- `contact.name` deve evitar placeholder.
- `contact.phone` deve vir normalizado quando houver.
- Enderecos devem ser lista serializavel para o app mobile.
- App pode usar telefone formatado como fallback de display name.

## Geo/Entrega

Estado desejado:

- Google como provider canonico se essa decisao for mantida.
- HERE deve ser documentado como legado ou removido gradualmente.
- Delivery fee deve ser fonte unica para storefront, WhatsApp agent e checkout.

Regras Cê Saladas recuperadas:

- R$ 9,00 ate 4 km.
- R$ 1,10/km adicional acima de 4 km.
- Aurenys/Bertaville: R$ 40,00.
- Taquaralto: R$ 40,00.
- Aeroporto: R$ 45,00.
- Luzimangues: R$ 45,00.
- Taquari: R$ 50,00.
- Caribe/Polinesia: R$ 25,00.
- Mirante do Lago: R$ 25,00.
- Alphaville/Privilege/Aldeia do Sol: taxa por km + R$ 5,00.
- Chuva: + R$ 2,00.

Nao expor regra interna no WhatsApp:

- O agente deve pedir endereco/localizacao para calcular.

## WhatsApp Agent

Regras para `Caio` / Cê Saladas:

- responder curto
- nao recomendar por perfil sem contexto
- nao assumir pedido a partir de sugestao
- nao falar de Pix cedo demais
- so pedir endereco depois que cliente escolher entrega
- nao gerar Pix sem pedido claro e codigo real

Guardrails recentes:

- gate de horario fora de funcionamento para intents elegiveis
- limite de tools por tipo de pergunta
- teste base: `tests/test_agent_runtime_guards.py`

## Realtime

Contratos conhecidos:

- `ws/stores/{store_slug}/orders/`
- `ws/whatsapp/{account_id}/`
- `ws/chat/{conversation_id}/`
- `ws/dashboard/`
- SSE fallback em `/api/sse/...`

Regra:

- mudanca em evento/realtime deve ser coordenada com `pastita-dash`.

## Smoke Tests Recomendados

Antes de deploy relevante:

1. OTP send/verify real ou sandbox com template.
2. Catalogo publico `ce-saladas`.
3. Perfil customer com usuario que tem `@pastita.local`.
4. Autosuggest/endereco para Palmas - TO.
5. Taxas fixas e taxa por km.
6. Checkout web guest.
7. Checkout mobile quando implementado.
8. WhatsApp agent:
   - `qual taxa de entrega?`
   - `quero 2 saladas e pagar no pix`
   - pedido ambiguo
9. Dashboard auth e overview.
10. Media WhatsApp no painel sem renderizar objeto JSON como React child.

