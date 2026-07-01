# Onboarding Profissional — Wizard + Guide Redesign — Design

**Data:** 2026-06-30
**Contexto:** A Fase 2 entregou um checklist funcional mas visualmente pobre (lista de emoji). Este projeto eleva o onboarding a padrão SaaS profissional: um **wizard de setup full-screen** (1º login) + o **guide/card redesenhado** (persistente, bonito). Mesma jornada, duas superfícies, **mesmo estado derivado** já existente.

## Objetivo

Um dono novo, logo após o cadastro, é levado por um wizard full-screen que configura a loja de verdade (logo, 1º produto, entrega, horário, WhatsApp) sem sair do fluxo — e, se pular, retoma a qualquer momento pelo card "Primeiros passos" no dashboard. Bonito, intuitivo, sem feiura.

## Decisões travadas (brainstorm)

1. **Wizard guiado full-screen** com mini-forms embutidos (não launcher que deep-linka).
2. **Auto-abre no 1º login** de loja incompleta; **retomável** pelo card (botão "Continuar configuração" reabre no 1º passo pendente).
3. **Mini-forms dedicados sobre os services existentes** — reusa a camada de dados (`storesApi`/`products`/`delivery`), presentation nova. Páginas admin pesadas ficam intactas.
4. **Só o card do dashboard** como guide persistente — sem página `/comecar` dedicada (menos é mais).
5. **Estado de "já viu o wizard" no backend** (`Store.onboarding_wizard_seen`, boolean) — **sem localStorage**. Substitui o dismiss-por-localStorage atual do card.

## Estado e fluxo (uma flag, sem localStorage)

- Novo campo `Store.onboarding_wizard_seen: BooleanField(default=False)` (migration de 1 campo).
- **Progresso** continua 100% derivado pelo `build_checklist` (Fase 2) — fonte única, nada duplicado.
- **Auto-abrir o wizard:** no load do dashboard, abre automaticamente quando `!checklist.all_done && !store.onboarding_wizard_seen`. **No momento do auto-open**, dispara `markWizardSeen` (`onboarding_wizard_seen=true`) → **auto-abre no máximo uma vez**, independente do dono concluir, pular ou fechar. Reabertura posterior é sempre manual (pelo card).
- **Card persistente:** aparece sempre que `!checklist.all_done` (independe da flag) — é o ponto de retomada. **Sem botão "dispensar"** (sumia via localStorage; agora some sozinho ao completar). O CTA "Continuar configuração →" reabre o wizard manualmente quando quiser.
- **Lojas já completas** (as 3 isentas, se `all_done`) → card não aparece.

## Arquitetura

### Backend (server2)
- `Store.onboarding_wizard_seen` (migration mínima).
- Expor o campo: incluir `onboarding_wizard_seen` no payload do checklist OU no serializer de Store já consumido pelo dash. **Decisão:** adicionar ao retorno de `build_checklist`/endpoint de onboarding (`{..., wizard_seen: bool}`) — mantém o dash com 1 fetch só. E um endpoint de escrita: `POST /api/v1/stores/<slug>/onboarding/seen/` (gated `_can_manage`) que seta `onboarding_wizard_seen=true`. Read-only do checklist permanece; a escrita é só essa flag.

### Frontend (pastita-dash) — `src/components/onboarding/`
- `wizard/OnboardingWizard.tsx` — shell full-screen (`@headlessui Dialog` + `framer-motion`): cabeçalho com logo + barra/anel de progresso animado; corpo que troca de passo com transição slide/fade; rodapé Voltar / Pular / Salvar e continuar.
- `wizard/steps/` — um arquivo por passo, cada um um mini-form dedicado que chama o service e reporta sucesso ao shell:
  - `StepLogo.tsx` → `updateStoreWithFiles` (drag-drop + preview)
  - `StepProduct.tsx` → service de produto (nome, preço, foto)
  - `StepDelivery.tsx` → cria zona (`delivery`) ou "só retirada"
  - `StepHours.tsx` → grade dias/horas → `updateStore(operating_hours)`
  - `StepWhatsApp.tsx` → número → `updateStore(whatsapp_number)`
  - `StepWelcome.tsx` / `StepDone.tsx` — abertura e conclusão.
- `wizard/useOnboardingWizard.ts` — hook de orquestração: estado do passo atual, deriva quais passos já estão feitos (via checklist), navega, dispara o `seen`, fecha.
- `OnboardingChecklist.tsx` (REDESENHO do componente da Fase 2) — card premium: anel de progresso (N/6), ícones **lucide** por passo (não emoji), linhas com check animado, CTA "Continuar configuração →" que abre o wizard no 1º pendente. Remove o uso de localStorage.
- `src/services/onboarding.ts` — adiciona `markWizardSeen(slug)` e, se necessário, o tipo `wizard_seen` no retorno do checklist.
- Montagem: `DashboardPage.tsx` já monta o card (Fase 2); passa a montar também o `OnboardingWizard` (controlado por estado derivado de checklist + wizard_seen).

### Reuso / isolamento
- **Data layer 100% reusado** (`storesApi`, `products`, `delivery`, `onboarding`) — zero lógica de API nova além do `markWizardSeen`.
- Cada passo é uma unidade isolada: recebe `onSaved()`, valida, chama 1 service, reporta. Testável sozinho.
- O shell não conhece a lógica de cada form; só orquestra navegação e progresso.

## Stack visual
`framer-motion` (transições de passo + progresso) · `@headlessui` Dialog (focus-trap, Esc, acessível) · `lucide-react` (ícones) · `cva`/`clsx`/`tailwind-merge` (variantes) · tokens dark-luxe (`bg-surface-token`/`text-fg-token`/`text-fg-muted-token`/`bg-brand`/`border-border-token`). **Sem dependência nova.**

## Erros e bordas
- Falha de save num passo → mensagem inline no passo, não avança, não perde o que foi digitado. Outros passos intactos.
- Fechar o wizard (X/Esc) → volta pro dashboard; card continua como retomada; `wizard_seen` já setado (não reabre sozinho).
- Passo já-feito (derivado) → vem pré-marcado, dono pode pular.
- `markWizardSeen` falha → silencioso (não bloqueia a UI); pior caso reabre uma vez a mais.
- Fetch do checklist falha → wizard não auto-abre e card não renderiza (home intacta), igual hoje.

## Testes
- **jest (dash):** cada mini-form (valida + chama o service mockado + chama `onSaved`); o shell (navega, pula, conclui, dispara `markWizardSeen`); o card redesenhado (anel/progresso, abre o wizard no 1º pendente, some em `all_done`). Output pristine (zero `act()` warning).
- **backend (Docker harness):** migration do campo; `build_checklist`/endpoint inclui `wizard_seen`; endpoint `onboarding/seen/` seta o campo e é gated `_can_manage` (403 não-owner).

## Fora de escopo (YAGNI)
Sem página `/comecar`, sem tour de tooltips, sem vídeo, sem multi-idioma, sem A/B, sem dismiss manual do card (some sozinho em 100%).

## Faseamento (pro plano)
- **Fase A — Guide redesign:** redesenha `OnboardingChecklist` (anel + ícones lucide + CTA), remove localStorage. Ganho visual imediato, baixo risco. (Backend: nada novo ainda; CTA pode abrir um placeholder até a Fase B.)
- **Fase B — Wizard:** campo `onboarding_wizard_seen` + endpoint `seen` + shell + 5 mini-forms + auto-open/retomada. Liga o CTA do card no wizard real.

## Constraints globais (herdadas)
- TDD; zero regressão. `is_staff` NÃO cross-tenant (`_can_manage`). Commits PT + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Dash: jest; `tsc --noEmit` 0; `vite.config.ts` fora dos commits; tokens dark-luxe. server2: harness `scripts/sdd-test.sh`; deploy `deploy.sh`.
