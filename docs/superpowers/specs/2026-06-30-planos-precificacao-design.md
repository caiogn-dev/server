# Spec — Redesenho de Planos e Precificação (Cardapidex SaaS)

**Data:** 2026-06-30
**Status:** Aprovado (design) — aguardando plano de implementação
**Repos afetados:** `server2` (catálogo + enforcement), `pastita-dash` (exibição /assinatura), `cardapidex-web` (landing/pricing)

## Objetivo

Substituir o catálogo de planos atual (Starter R$59 / Pro R$99 / Premium R$159, com adesão genérica em todos) por uma estrutura **ancorada em valores reais de mercado** (não números arbitrários), com posicionamento de conversão claro e um plano **Grátis** de aquisição.

## Contexto de mercado (pesquisa 2025/2026, concorrentes BR)

Levantamento dos principais SaaS de cardápio digital/delivery BR (Goomer, Anota AI, Cardápio Web, Cardápio Space, iFood loja própria, Neemo, Menu Dino, etc.). Achados que guiaram as decisões:

1. **Taxa de adesão NÃO é prática visível** — nenhum concorrente anuncia adesão. Cobrar adesão genérica na entrada deixaria o Cardapidex mais caro/estranho que todos e prejudicaria conversão. Vender "adesão zero" também é fraco (o cliente não vê os outros cobrando).
2. **Free converte** — o limitador real do mercado é **pedidos/mês (~30)** ou nº de itens, nunca marca d'água. Free permanente e generoso diferencia.
3. **Bot WhatsApp + IA de verdade é o maior gap** — só a Anota AI tem como core, cobrando **R$280–400**. Cardapidex já entrega bot+IA → é a âncora de valor premium.
4. **Âncora psicológica de entrada = R$99,90** (Goomer). Abaixo de ~R$49 vira segmento "QR-code barato"; miolo de valor real é R$130–300; topo R$300–449.
5. **0% de comissão** vende sozinho contra o iFood (12–27%).

## Posicionamento

**"Tudo incluso, 0% de comissão, com bot + IA."** (Não "adesão zero".) Ataca o modelo à-la-carte de concorrentes que inflam o ticket com módulos cobrados à parte, e o gap de IA conversacional do mercado.

## Estrutura de planos (aprovada)

| | **Grátis** | **Essencial** | **Pro** | **Premium** |
|---|---|---|---|---|
| Chave interna | `free` | `starter` | `pro` | `premium` |
| Nome exibido | Grátis | Essencial | Pro | Premium |
| Mensal | R$ 0,00 | R$ 99,90 | R$ 249,00 | R$ 349,00 |
| Adesão (única) | — | — | — | R$ 149,00 (= domínio + setup) |
| Pedidos/mês | 30 | ilimitado | ilimitado | ilimitado |
| Produtos | 40 | ilimitado | ilimitado | ilimitado |
| Comissão por pedido | 0% | 0% | 0% | 0% |
| Bot WhatsApp | ❌ | ❌ | ✅ | ✅ |
| Agente IA | ❌ | ❌ | ❌ | ✅ |
| Domínio próprio | ❌ | add-on | add-on | ✅ incluso |

**Justificativa dos números:** Essencial em R$99,90 é a âncora de entrada do mercado (subir a porta de entrada espanta o lojista pequeno que migra do cardápio grátis). Pro R$249 (bot) e Premium R$349 (bot+IA) ficam **abaixo do teto da Anota AI (R$400)** entregando mais (bot+IA+domínio+0% comissão). A adesão sobrevive **só no Premium** porque está amarrada a uma entrega concreta (registro + configuração do domínio), não é taxa genérica.

## Decisões de empacotamento

- **Adesão:** removida de Essencial/Pro. Mantida **só no Premium**, R$149 única, cobrindo registro + configuração do domínio próprio (1º ano). Gate técnico permanece o duplo: `BILLING_SETUP_FEE_ENABLED` (env) + `charges_setup_fee` por plano.
- **Domínio próprio:** incluso no Premium; disponível como **add-on avulso** (R$149 única, registro+config 1º ano) para Essencial/Pro. Renovação anual posterior: a definir (por conta do lojista ou inclusa enquanto assinar) — fora do escopo deste 1º ship.
- **Grátis:** isca de aquisição. Limite de **30 pedidos/mês** e **40 produtos**. Ao estourar o limite de pedidos no mês, bloqueia novos pedidos e exibe o PaywallModal ("suba pro Essencial") — reaproveita o componente existente.

## Mudanças técnicas (alto nível — detalhar no plano)

### server2 (`apps/stores/billing.py` + enforcement)
- `PLAN_CATALOG`: adicionar chave `free`; ajustar valores `monthly_price`/`setup_fee`/`charges_setup_fee`/limits dos 3 existentes conforme tabela. Mudar `name` de `starter` para "Essencial". Manter chaves `starter`/`pro`/`premium` (evita migration de `Store.plan`).
- **NOVO gate — limite de pedidos/mês:** hoje existe só `within_product_limit`. Criar `limits.max_orders_per_month` (`None` = ilimitado) e enforcement na criação de pedido (contar pedidos da loja no mês corrente; isento e planos pagos passam). Ao exceder → 400 com `detail` que o front detecta (padrão do PaywallModal).
- `free` com `max_products: 40`, `max_orders_per_month: 30`, todas as features booleanas `False`.
- **Invariante sagrado mantido:** `billing_exempt=True` curto-circuita TUDO (as 3 lojas reais nunca afetadas). Lojas em `free`/qualquer plano só são limitadas se NÃO isentas.

### pastita-dash (`/assinatura`, landing de planos)
- A página já consome `getPlans()` + `SubscriptionStatus`; ela reflete o catálogo automaticamente. Validar exibição do `free` e dos novos valores. Ajustar copy de posicionamento.

### cardapidex-web (landing)
- Seção de planos/pricing reflete a nova tabela + posicionamento "tudo incluso, 0% comissão, bot+IA".

## Migração / impacto em lojas existentes

- **3 lojas reais** (ce-saladas, kero-kero, pastita): `billing_exempt=True` — **intocadas**, não entram em nenhum plano/limite.
- **Lojas não-isentas existentes** (ex.: ivoneth-banqueteria, zz-teste-billing): hoje `trialing` sem `trial_ends_at`. Definir no plano: ficam em qual plano default ao fim do trial? (Recomendado: `free`, para não cobrar surpresa.)
- Chaves de plano inalteradas (`starter`/`pro`/`premium`) → `Store.plan` existente continua válido; só muda preço/nome exibido e entra o `free`.

## Fora de escopo (futuro)

- Preço anual / desconto anual.
- Renovação automática do domínio após o 1º ano.
- Reprecificação das 3 lojas reais (decisão separada; seguem isentas).
- Go-live de cobrança real (Task 13: env + webhook MP + smoke test) — depende deste catálogo fechado.

## Critérios de sucesso

- Catálogo reflete a tabela aprovada; `GET /public/plans/` retorna os 4 planos com valores corretos.
- Loja `free` não-isenta é bloqueada ao exceder 30 pedidos/mês ou 40 produtos, com paywall.
- Loja isenta nunca é limitada/cobrada, em qualquer plano.
- Premium cobra adesão (R$149) só com `BILLING_SETUP_FEE_ENABLED=true`; demais planos nunca cobram adesão.
- Zero regressão nos testes de billing/assinatura existentes.
