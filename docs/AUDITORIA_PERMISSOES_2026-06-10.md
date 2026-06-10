# Auditoria de Permissões e Exceções Silenciosas — 2026-06-10

Escopo: 64 usos de `AllowAny` e exceções silenciadas (`except: pass`) no server2.
Veredito por arquivo: **JUSTIFICADO** (público por design) ou **SUSPEITO** (corrigir).

## AllowAny — classificação

| Arquivo | Usos | Veredito | Justificativa |
|---|---|---|---|
| `apps/public_api/views.py` | 12 | JUSTIFICADO | Storefront público por design (`/api/v1/public/{slug}/`), read-only, throttle `public_read` |
| `apps/stores/api/views/storefront_views.py` | 8 | JUSTIFICADO | Catálogo/carrinho guest (checkout sem cadastro é requisito do produto) |
| `apps/stores/api/maps_views.py` | 6 | JUSTIFICADO c/ ressalva | Geocode/rota para checkout guest. Coberto pelo throttle global anon 120/min. **Ressalva:** chama APIs pagas (Google Maps) — considerar throttle scope dedicado mais restritivo (ex. 30/min) p/ conter abuso de custo |
| `apps/stores/api/views/print_views.py` | 5 | JUSTIFICADO | `AllowAny` é só no DRF; autenticação real é por API key de agente (`_get_agent_from_request` → 401 sem key válida) |
| `apps/automation/webhooks/views.py` | 5 | JUSTIFICADO | Webhooks externos não autenticam via DRF; validação por assinatura/token próprio |
| `apps/core/auth_views.py` + `apps/core/auth/views.py` | 8 | JUSTIFICADO | Login/OTP precisam ser públicos; throttle `auth` 10/min |
| `apps/stores/api/views/combo_views.py` | 3 | JUSTIFICADO | Catálogo público de combos |
| `apps/core/health_views.py` | 3 | JUSTIFICADO | Healthchecks (Uptime-Kuma/monitoring) |
| `apps/core/api.py` | 3 | JUSTIFICADO | CSRF/bootstrap público |
| `apps/instagram/api/data_deletion_view.py` | 3 | JUSTIFICADO | Callback obrigatório da Meta (data deletion) |
| `apps/whatsapp/webhooks/views.py` | 2 | JUSTIFICADO | Webhook Meta — agora **fail-closed** (commit 252475e): sem `WHATSAPP_APP_SECRET` rejeita |
| `apps/notifications/api/views.py` | 2 | JUSTIFICADO | `vapid_public_key` retorna chave pública (não sensível) |
| `apps/postado/api/views.py` | 3 | **SUSPEITO** | `PostadoMPWebhookView` aceita webhook MercadoPago **sem verificação de assinatura** — forjável. Impacto baixo (só dispara `generate_pack` p/ cliente existente, idempotente por mês), mas deve validar `x-signature` como o dispatcher central. **Recomendação:** migrar p/ `/webhooks/v1/mercadopago/` (dispatcher central, fail-closed) ou replicar a validação HMAC |

**Resumo:** 61/64 justificados (público por design, com throttle). 3 suspeitos no `postado` (webhook MP sem HMAC — recomendação registrada acima; app é secundário, sem dinheiro de cliente da plataforma).

## except: pass / bare except

A maioria dos 21 `except: pass` captura exceções **tipadas** (`DoesNotExist`, `ValueError`) em caminhos onde ignorar é o comportamento correto — não são bugs.

Corrigidos neste commit:
- `apps/whatsapp/tasks/__init__.py:195` — bare `except: pass` ao enviar fallback do agente → agora `except Exception` + `logger.exception`
- `apps/whatsapp/tasks/__init__.py:421` — bare `except` em parse de quantidade → tipado `(ValueError, TypeError)`
- `apps/whatsapp/services/webhook_service.py` — `validate_signature` fail-open → fail-closed (commit 252475e)

Restantes aceitáveis (baixo risco, fora de fluxo de pagamento):
- `apps/whatsapp/management/commands/force_delete_account.py` (4×) — comando manual de limpeza
- `apps/handover/consumers.py:123` — cleanup de WebSocket em disconnect
- `apps/core/health_views.py:119` — healthcheck não deve propagar exceção

## Ações pendentes do operador

1. (Opcional, custo) Criar throttle scope dedicado p/ maps_views (~30/min).
2. (Recomendado) Migrar webhook do Postado para o dispatcher central com HMAC.
