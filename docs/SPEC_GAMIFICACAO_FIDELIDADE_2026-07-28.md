# Spec — Gamificação & Fidelização (Fase 1)

**Data:** 2026-07-28 · **Escopo:** plataforma Cardapidex (multi-tenant), ce-saladas como primeira loja ativa · **Objetivo:** conversão e recompra

## Contexto

O motor de fidelidade "compre N ganhe 1" **já existe e roda em produção** no server2, invisível para o cliente:

- Modelos: `StoreLoyaltyAccount` + `StoreLoyaltyTransaction` (`apps/stores/models/loyalty.py`) — saldo materializado, trilha auditável, idempotência por pedido.
- Serviço: `LoyaltyService` (`apps/stores/services/loyalty_service.py`) — threshold por loja em `store.metadata['loyalty_salads_required']` (default 10), `loyalty_enabled` (default True).
- Endpoints já roteados: `GET /api/v1/stores/{slug}/loyalty/` e `GET .../loyalty/redeem-check/`.
- Cupons existem e foram consertados em 27/jul (campos mortos/burláveis).
- **Nenhuma UI** em cardapidex-web, ce-saladas ou pastita-dash consome nada disso.

A Fase 1 é **expor o que existe** + cupons que convertem + mensagens proativas de recompra via WhatsApp oficial.

## Decisões tomadas

1. **Feature de plataforma**, não hack do ce-saladas: configurável por loja no dash; vira argumento de venda dos planos.
2. **Web primeiro** (cardapidex-web); Flutter e superfícies extras depois.
3. **WhatsApp: só canal oficial (Meta Cloud API) na Fase 1.** Mensagens proativas fora da janela de 24h via **templates aprovados** (Utility para lembrete de carrinho sem cupom; Marketing para cupom/reativação). Volume por loja é pequeno → custo de centavos/mês. **Evolution API/Baileys fica fora da Fase 1**: números das lojas são Cloud API (sem sessão de app para parear QR) e o risco de ban recai sobre o número que fecha pedidos. Fica previsto como provider plugável futuro no `apps.messaging` para cenário de escala/número secundário.
4. Ganchos `wa.me` nas superfícies (cupom impresso, página de sucesso) para o **cliente** abrir a janela de 24h — conversa livre de graça.

## Escopo Fase 1

### A. Storefront (cardapidex-web)

**A1. Cartão de progresso de fidelidade** — cliente logado vê no cardápio e na sacola: "🥗 7/10 — faltam 3 para sua salada grátis", com barra de progresso. Fonte: `GET /loyalty/`. Cores 100% do tema da loja (regra vigente: zero hardcoded). Cliente deslogado com programa ativo vê teaser ("Entre e junte saladas — a 10ª é grátis").

**A2. Resgate no checkout** — quando `can_redeem: true`, o passo 1 do checkout exibe "Você tem 1 salada grátis 🎉 — usar agora?". Aplicar = desconto do item qualificado mais barato do carrinho; backend registra via `LoyaltyService.redeem` **dentro do fluxo de criação do pedido** (não em request separado, para não queimar resgate de pedido não concluído). Validação server-side sempre; `redeem-check` é só pré-visualização.

**A3. Banner de cupom ativo** — loja com cupom marcado como "destaque" exibe faixa no topo do cardápio (ex.: "Primeiro pedido? BEMVINDO10 = 10% off"). Requer flag nova no cupom (`is_featured` ou metadata) exposta no endpoint público da loja.

### B. Dash (pastita-dash)

**B1. Página "Fidelidade & Cupons"** (rota nova, navbar via `buildNavSections`):
- Toggle do programa + threshold N (grava `store.metadata`).
- Regra de qualificação: por categoria ou produto (quais itens contam). Hoje o serviço conta itens qualificados — a definição do que qualifica precisa ficar configurável (novo campo em metadata, ex. `loyalty_qualifying_categories: [ids]`; vazio = tudo qualifica).
- Lista de contas de fidelidade da loja (cliente, progresso, resgates) — endpoint novo de listagem, paginado, escopado à loja.
- Criação rápida de cupom de boas-vindas (1 clique gera cupom first-order com % configurável) + toggle "destacar no cardápio".

### C. WhatsApp (Meta oficial)

**C1. Resposta de saldo** — intent "fidelidade/pontos/saldo/cartão" no bot responde status formatado (dentro da janela, grátis).

**C2. Linha de fidelidade na confirmação de pagamento** — mensagem de pedido pago que o bot já envia ganha: "🥗 8/10 no seu cartão — faltam 2!". Carona em mensagem existente, custo zero.

**C3. Carrinho abandonado** — task Celery existente (varredura 5min) ganha dispatch WhatsApp: template Utility "seu carrinho está salvo: {{link}}" (sem cupom). Variante com cupom (template Marketing) configurável por loja. Regras: 1 mensagem por carrinho, cooldown 24h por cliente, respeita opt-out.

**C4. Reativação** — task diária: cliente com ≥1 pedido pago e sem pedido há N dias (default 21, configurável) recebe template Marketing com cupom "sentimos sua falta". Máx. 1 reativação por cliente a cada 45 dias.

**C5. Fidelidade proativa** — `can_redeem` true há X dias sem resgate → template Marketing "sua salada grátis está liberada 🥗". 1 disparo por prêmio.

**Guard-rails de envio (todos os proativos):** opt-out por resposta "SAIR" (flag no cliente, respeitada em todo canal de marketing); kill-switch por loja no dash; teto diário por loja; log de cada disparo (auditoria + relatório).

### D. Gate por plano

- Fidelidade visível (A1/A2, B1 básico, C1/C2): **todos os planos** — vitrine da plataforma.
- Proativos C3/C4/C5 + banner A3: **Pro e Premium** (alinha com go-live de cobrança).
- Enforcement no backend (não só esconder botão no dash).

## Fora de escopo (Fase 2+)

Indicação ("indique e os dois ganham"), review invite pós-entrega com recompensa, metas de ticket na sacola ("faltam R$ 12 pro frete grátis"), streaks/desafios, Evolution API como provider de escala, Flutter.

## Arquitetura / pontos de implementação

- **server2**: novos campos de config em `store.metadata` (lidos por `LoyaltyService._config`); qualificação configurável no crédito (`credit_qualified` — hoje o chamador decide a quantidade; centralizar regra num helper `count_qualifying_items(order, store)`); endpoint de listagem de contas (dash); flag destaque no cupom + exposição pública; templates Meta registrados por loja (aproveitar infra do `codigo_verificacao`); tasks C3/C4/C5 nas filas Celery existentes (`whatsapp`/`automation`); modelo/flag de opt-out marketing no cliente + log de disparos.
- **cardapidex-web**: componentes de progresso/resgate/banner consumindo endpoints públicos+auth existentes; tema dinâmico.
- **pastita-dash**: página nova + service; navbar via `buildNavSections`; gating progressivo (padrão `useAutomationEnabled`).
- **Deploy**: server2 = imagem baked + deploy.sh (regra docker cp/commit); dash = push main (Vercel); web = systemd restart.

## Testes (TDD, regra do projeto)

- Backend: qualificação configurável (categoria conta / não conta), resgate atômico no checkout (sem saldo → erro; pedido falho → não queima resgate), idempotência de crédito, opt-out bloqueia proativo, gate por plano nega C3-C5 em plano Grátis/Essencial, cooldowns (C3 24h, C4 45d, C5 1x por prêmio).
- Dash: Jest para página nova (padrão das demais).
- Baseline: suíte server2 sem regressão (gate = zero falha nova vs baseline).

## Métricas de sucesso

- % de pedidos com resgate aplicado; taxa de recuperação de carrinho abandonado (meta inicial: >10%); taxa de retorno pós-reativação; nº de lojas com programa ativo.
