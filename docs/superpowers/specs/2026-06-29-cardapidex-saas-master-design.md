# Cardapidex SaaS — Plano Mestre de Finalização

**Data:** 2026-06-29
**Escopo:** cross-repo (`server2`, `pastita-dash`, `cardapidex-web`)
**Tipo:** finalização e conexão de camada SaaS existente — NÃO reconstrução

---

## 1. Contexto

Cardapidex (ex-Pastita) é um SaaS multi-tenant para restaurantes/lojas de delivery,
em 3 repositórios:

- **server2** — API Django/DRF + billing (canônico)
- **pastita-dash** — painel do lojista (React/Vite, `painel.cardapidex.com.br`, deploy Vercel)
- **cardapidex-web** — storefront + site institucional/marketing (Next/React)

Hoje rodam 3 lojas reais (Cê Saladas é a única com receita real), **todas isentas**
(`billing_exempt=True`) e **fora deste plano** — grandfather fixo, ninguém encosta.

### Diagnóstico (auditoria de código, 2026-06-29)

O SaaS **não está mal feito — está ~80% construído e desconectado**. O motor existe;
falta o que transforma trial em receita recorrente e em loja ativada.

**Já existe e funciona (não refazer):**
- Catálogo de 3 planos + limites (`server2/apps/stores/billing.py`)
- Modelo `StoreSubscription` (`server2/apps/stores/models/subscription.py`)
- Campos na Store: `trial_ends_at`, `plan`, `billing_exempt`, `onboarding_completed`
- Signup self-service (`owner_signup`, cria user+loja em trial 14d)
- Endpoint público de planos (`/api/v1/public/plans/`)
- **Assinatura recorrente MercadoPago JÁ integrada**: preapproval + webhook com
  validação HMAC + mapeamento `authorized/paused/cancelled` → status
- `PlanoPage.tsx` no dash já redireciona pro checkout MP
- Trial banner com contagem; enforcement de limite de produtos no backend

**Lacunas (origem da dor "cobrar de quem já está"):**
A cobrança automática nunca foi **ligada em produção** — por isso ninguém é cobrado
de fato, não por falta de quem pague.

| Lacuna | Pilar | Status atual |
|--------|-------|--------------|
| Trial não expira sozinho (sem Celery task) | Monetização | stub |
| Setup fee (adesão) não é cobrada | Monetização | TODO no código |
| Sem dunning (falha de cobrança mensal) | Monetização | falta |
| Sem gestão pós-assinatura (faturas, cancelar, up/downgrade, cartão) | Monetização | falta |
| Paywall cru (erro 400, sem modal de upgrade) | Monetização | falta |
| `onboarding_completed` nunca vira true | Ativação | falta |
| Sem wizard de setup e sem tour | Ativação | falta |
| Landing/pricing estáticas; cadastro mora no dash | Aquisição | parcial |

---

## 2. Objetivo

Transformar "trial → cliente pagante recorrente" num funil completo e profissional,
atravessando os 3 repos, **priorizando o caminho mais curto até a primeira cobrança
recorrente real em produção**.

---

## 3. Decisões de produto (travadas)

- **Lojas existentes:** as 3 reais ficam **isentas pra sempre** (`billing_exempt=True`),
  fora deste plano. A máquina mira **toda loja nova** que entra pelo funil.
- **Fim do trial sem assinatura:** carência de **3 dias** (configurável) com aviso →
  só então **suspende** a loja.
- **Taxa de adesão (setup fee):** **cobrada de verdade** (1ª fatura/preference separada
  no MP) **+ toggle por plano** para ligar/desligar a cobrança da adesão.
- **Sequência:** "dinheiro primeiro" — Monetização → Ativação (guide) → Aquisição.

---

## 4. Arquitetura das fases

```
FASE 1 — Fechar o loop de cobrança recorrente   (Monetização)  ← começa aqui
FASE 2 — Guide / ativação (wizard + tour)        (Ativação)
FASE 3 — Aquisição (landing/pricing/cadastro)    (Aquisição)
```

Cada fase entrega valor sozinha e tem critério de "pronto".

### FASE 1 — Loop de cobrança recorrente

**Objetivo:** uma loja nova consegue, sozinha, sair do trial e virar assinante recorrente
pago — e quem não paga é barrado. Em produção, sem tocar nas 3 isentas.

| # | Bloco | Entrega | Repo |
|---|-------|---------|------|
| 1.1 | Task de expiração de trial | Celery beat diário: trial vencido + sem assinatura ativa → entra em carência (3d) → `suspended` | server2 |
| 1.2 | Enforcement de suspensão | Loja suspensa: storefront recusa pedidos; painel mostra "reative assinando" | server2 + web + dash |
| 1.3 | Dunning | Webhook de fatura falha → `past_due`, avisa, X dias, depois suspende | server2 |
| 1.4 | Gestão de assinatura | Página no painel: status, próxima cobrança, cancelar, up/downgrade | dash |
| 1.5 | Paywall com UX | Bater no limite → modal "faça upgrade" em vez de erro 400 | dash |
| 1.6 | Setup fee + autocharge em produção | Wiring da 1ª fatura de adesão + toggle por plano; ligar `BILLING_AUTOCHARGE_ENABLED=true`; validar webhook real; smoke test ponta a ponta | server2 (config/deploy) |

**Pronto quando:** loja teste nova → trial → assina → MP cobra recorrente em produção →
se cancelar/falhar, é suspensa automaticamente (após carência). Provado com teste real.

### FASE 2 — Guide / ativação (wizard A + tour B)

**Objetivo:** loja recém-criada sai de "conta vazia" até "publicada e vendendo" sozinha;
`onboarding_completed` passa a virar true de verdade.

| # | Bloco | Entrega | Repo |
|---|-------|---------|------|
| 2.1 | Backend de progresso | Endpoint que calcula estado de cada passo (cardápio? horário? entrega? pagamento? publicada?) e expõe/persiste `onboarding_completed` | server2 |
| 2.2 | Wizard de setup (A) | Checklist com barra de progresso: cardápio → horários → entrega/taxa → pagamento → publicar; "faltam N passos pra ir ao ar" | dash |
| 2.3 | Tour guiado (B) | Spotlight/tooltips por cima da UI; pós-wizard ou on-demand | dash |
| 2.4 | Conexão com trial | Wizard/banner amarra ativação ↔ trial ("dia 5/14, publique sua loja") | dash |

**Pronto quando:** loja nova publica sem suporte humano e `onboarding_completed` vira
true sozinho.

### FASE 3 — Aquisição (funil de cadastro)

**Objetivo:** visitante do site institucional vira loja em trial sem intervenção.

| # | Bloco | Entrega | Repo |
|---|-------|---------|------|
| 3.1 | Pricing dinâmico | Landing puxa planos de `/api/v1/public/plans/` (hoje preço estático duplica o backend) | web |
| 3.2 | Cadastro polido | Fluxo `/cadastro` revisado: validação, erros, sucesso → cai no wizard da Fase 2 | dash + web |
| 3.3 | Landing que converte | Hero, prova social, CTA, "como funciona" amarrado ao guide | web |
| 3.4 | Emails transacionais | Boas-vindas; "trial acaba em 3 dias"; "loja suspensa, reative" | server2 |

**Pronto quando:** dá pra mandar tráfego e medir visitante → trial → loja publicada →
assinante.

---

## 5. Restrições

- **TDD** — testes antes do código; zero regressão.
- **Zero regressão nas 3 lojas vivas** — grandfather (`billing_exempt`) não pode quebrar.
- **Commits em PT.**
- **Deploy seguro** — server2 imagem baked (`deploy.sh`); dash via Vercel (push na main);
  cuidado com disco no build do server2.
- **Não reescrever o que funciona** — finalizar e conectar o que está pela metade.

---

## 6. Riscos

- **Ligar autocharge em produção** sem smoke test real pode cobrar/suspender errado →
  validar com loja teste dedicada antes de abrir.
- **Suspensão indevida** de loja isenta → garantir que toda checagem de trial/suspensão
  curto-circuita em `billing_exempt=True`.
- **Webhook MP em produção** depende de `MERCADO_PAGO_WEBHOOK_SECRET` correto
  (fail-closed) e da URL pública de webhook acessível.
- **Disco do server2** no build/deploy (histórico de crash de Postgres por falta de espaço).

---

## 7. Fora de escopo (YAGNI por enquanto)

- Cobrar as 3 lojas grandfather (outro caso, decisão futura).
- Relatório/admin de receita (pode entrar depois da Fase 1 se necessário).
- Multi-moeda, planos anuais, cupons de desconto.
- Login de cliente final no storefront (segue guest-checkout).
