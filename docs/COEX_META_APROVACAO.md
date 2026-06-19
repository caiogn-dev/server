# COEX (WhatsApp Coexistence) — Plano de Aprovação Meta + Integração

> Objetivo: usar o WhatsApp Business App **junto** com a Cloud API (Coexistence),
> onboarding via **QR code** (Embedded Signup). Hoje a app Meta NÃO está aprovada
> para Advanced Access das permissões de WhatsApp. Este doc é o caminho.

## Estado atual (2026-06-16)
- ✅ Mensageria funciona: send text/template/interactive/image/document (`apps/whatsapp/services/whatsapp_api_service.py`) + webhook com `hub.challenge` (`apps/whatsapp/webhooks/views.py`).
- ✅ Data deletion: `apps/instagram/.../data-deletion/` + LGPD `request_deletion`.
- ✅ Privacy: cardapidex-web rota `/privacidade` (confirmar conteúdo).
- ❌ Embedded Signup / OAuth Meta: NÃO existe (é a parte de integração).
- ⚠️ Confirmar: `META_APP_ID` configurado, app em modo Live, Business Verification.

---

## FASE 1 — Pré-requisitos (destravar o App Review)

1. **Business Verification** (Meta Business Manager → Configurações → Verificação do negócio)
   - CNPJ, razão social, endereço, telefone/site que batem com documento.
   - Sem isso = preso em acesso limitado. É o gargalo nº1 silencioso.
2. **App em modo Live** (não Development) no developers.facebook.com.
3. **Privacy Policy URL** pública: `https://cardapidex.com.br/privacidade` (confirmar que está no ar e cobre coleta/uso/exclusão de dados do WhatsApp).
4. **Data Deletion**: já existe — apontar a URL nas configurações do app.
5. **Ícone, categoria, caso de uso** preenchidos no app.

## FASE 2 — App Review (Advanced Access)

Permissões a solicitar:
- `whatsapp_business_messaging` — enviar/receber mensagens.
- `whatsapp_business_management` — gerenciar WABA/números/templates.
- (Coexistence também usa `business_management`.)

**O GATE É O SCREENCAST.** Causa nº1 de reprovação = vídeo que não mostra a
permissão sendo usada de verdade. Roteiros na Fase 3.

## FASE 3 — Roteiros dos vídeos de teste (gravar 1 por permissão)

### Vídeo A — `whatsapp_business_messaging`
Mostrar o fluxo real ponta a ponta:
1. Logar no painel (painel.cardapidex.com.br) — mostrar a tela.
2. Abrir uma conversa / inbox do WhatsApp no painel.
3. **Cliente envia** mensagem no WhatsApp → aparece no inbox (mostra o webhook recebendo).
4. **Operador responde** pelo painel → chega no WhatsApp do cliente (mostra o send).
5. Mostrar o bot/automação respondendo (intent → resposta) se aplicável.
   - Narração/legenda: "Usamos whatsapp_business_messaging para receber mensagens
     de clientes e responder pedidos."

### Vídeo B — `whatsapp_business_management`
1. No painel, mostrar a tela de **configuração da conta WhatsApp** (número, status).
2. Mostrar **templates** (listar / status de aprovação) sendo lidos via API.
3. Se houver: cadastro/refresh de número ou consulta de WABA.
   - Narração: "Usamos whatsapp_business_management para gerenciar a conta,
     número e templates da loja."

**Regras dos vídeos:** fluxo real (não slides), mostrar o login → ação → resultado,
1-3 min cada, sem cortes que escondam a permissão em uso. Inglês ou PT com legenda.

## FASE 4 — Coexistence (QR) — pré-requisitos do NÚMERO
- Número ativo no **WhatsApp Business App há ≥ 7 dias**, última versão, celular com câmera.
- **Página do Facebook vinculada** ao WhatsApp Business App.
- Número **nunca registrado na Cloud API/WABA** antes (senão deletar WABA, re-registrar no app, esperar 1–2 meses).
- Região não-restrita; Business Manager dono do número.

## FASE 5 — Integração (código, depois da aprovação)
- Implementar **Embedded Signup** (JS SDK do Facebook no front + troca de code→token no server2).
- Fluxo Coexistence: compartilhar número → QR → código de confirmação no app → sincroniza histórico.
- Backend: endpoint OAuth callback, `debug_token`, persistir WABA/phone_number_id por loja (multi-tenant), assinar webhook do novo número.
- Cobrança: mensagens enviadas pelo App seguem grátis; conversas abertas via API entram na cobrança por conversa.

## Permissões a pedir no App Review — SÓ ESTAS 2
- `whatsapp_business_messaging` (core: enviar/receber, registrar número, automessage de pedido)
- `whatsapp_business_management` (Embedded Signup/Coex, templates, webhook subscription)
- **REMOVER da submissão:** `business_management`, `email`, `manage_app_solution`, `whatsapp_business_manage_events` (não usados; só aumentam superfície de reprovação). `public_profile` é auto.

## Gravação com NÚMERO DE TESTE do Meta (Development mode — chamada real, sem aprovação)

### Lado Meta (developers.facebook.com → seu app → WhatsApp → API Setup)
1. Use o **número de teste** gratuito → anote `phone_number_id` e `WABA ID`.
2. Gere o **token temporário** (validade 24h) na tela API Setup.
3. Em "Send and receive messages" → **To**: adicione seu **celular pessoal** como destinatário de teste (recebe código de confirmação).
4. Configuration → Webhooks:
   - Callback URL: `https://backend.pastita.com.br/webhooks/v1/whatsapp`
   - Verify token: `WHATSAPP_WEBHOOK_VERIFY_TOKEN` (ver no .env do server2)
   - Assinar o campo **`messages`**.

### Lado painel (pastita-dash → Mensageria/Conexões → adicionar conta)
Campos do `WhatsAppAccount`: `name`, `phone_number_id`, `waba_id`, `phone_number`, `access_token` (o temporário). Endpoint: `WhatsAppAccountViewSet` (POST).

### Roteiro Vídeo A — whatsapp_business_messaging (~2 min)
1. Login no painel (mostrar a URL/tela).
2. Abrir a aba Inbox/Conversas do WhatsApp.
3. Do **celular pessoal**, mandar "Oi, quero fazer um pedido" pro número de teste → mostrar **chegando no inbox** (webhook real).
4. **Responder pelo painel** → mostrar chegando no celular (send real).
5. (Se aplicável) mostrar o bot respondendo automaticamente.
6. Narração: "whatsapp_business_messaging é usado para receber mensagens de clientes e responder/automatizar pedidos."

### Roteiro Vídeo B — whatsapp_business_management (~1.5 min)
1. Painel → tela de **conta WhatsApp** (número, status, conectado via API).
2. Painel → **Templates** (Marketing → WhatsApp Templates) listando templates e status (lido via API).
3. Narração: "whatsapp_business_management é usado para gerenciar a conta, número e templates da loja."

## Ordem recomendada
1. Business Verification + app Live + privacy URL (Fase 1) — destrava tudo.
2. Gravar os 2 vídeos (Fase 3) com o fluxo que já funciona.
3. Submeter App Review.
4. (Aprovado) Implementar Embedded Signup/Coexistence (Fase 5).
