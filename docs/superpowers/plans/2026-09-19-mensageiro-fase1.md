# Mensageiro — Fase 1: um canal só para toda mensagem automática

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toda mensagem automática de WhatsApp (lembretes de PIX e de carrinho, reengajamento, status do pedido, pedido de avaliação) sai por um único canal que grava a mensagem na conversa, marca que é automática e trata falha do mesmo jeito — sem mudar o texto nem quando cada mensagem sai.

**Architecture:** Novo pacote `apps/automation/mensageiro/` com duas peças pequenas: `trava.py` (a reserva de "só uma vez" que hoje cada tarefa reimplementa com `cache.add`/`cache.delete`) e `canal.py` (envio pelo `MessageService`, que grava a mensagem, com `metadata.automatico=True`). As tarefas de `apps/whatsapp/tasks/automation_tasks.py` passam a chamar o canal, uma por tarefa, com teste de caracterização antes. É a fase 1 de um estrangulamento: comportamento preservado, o que muda é que a mensagem passa a existir no painel.

**Tech Stack:** Django 5, Celery, pytest (container `pastita_backend:latest`, banco `pastita_test_db` na rede `sdd_test_net`).

**Spec:** a seção "Desenho" abaixo, que resume a análise de 19/09/2026 (memória `project_mensagens_automaticas_duplicadas_set19.md`).

## Global Constraints

- Nenhum texto enviado ao cliente muda nesta fase. Nenhum horário/gatilho muda. Nenhuma trava nova é ligada (opt-out, modo humano, silenciar) — isso é a fase 2 e depende do dono.
- Mensagem automática NÃO atualiza `Conversation.last_agent_message_at`: esse campo diz "uma pessoa da loja respondeu" para a Fila humana (`apps/conversations/services/fila_humana.py`).
- Toda tarefa migrada mantém: idempotência (mesma chave e TTL de hoje), liberar a trava só se nada saiu, `self.retry` em falha.
- Rodar testes: `cd /home/graco/WORK/server2 && docker run --rm --network sdd_test_net -v "$PWD:/app" -w /app --entrypoint /opt/venv/bin/python -e DJANGO_SETTINGS_MODULE=config.settings.test --env-file .env -e TEST_DB_HOST=pastita_test_db pastita_backend:latest -m pytest <alvo> -q --no-header -p no:randomly --reuse-db`
- Deploy do server2: `docker cp` nos 3 containers (web, celery, celery_beat), paridade md5 git × 3 containers = 0, restart, `docker commit` (ver memória `feedback_deploy_paridade_3_containers.md`).
- Commits em `development`, `git add <caminhos explícitos>`.

---

## Desenho

**Problema medido (19/09):**
- 6 envios automáticos em `automation_tasks.py` chamam `WhatsAppAPIService` direto: a mensagem sai mas não é gravada. Log: 79 lembretes/reengajamentos em 30 dias; nas conversas do painel, 1. O atendente não vê que o bot mandou lembrete.
- Os envios que já gravam (status do pedido, avaliação) atualizam `last_agent_message_at`: um "saiu para entrega" tira o cliente da Fila humana como se alguém tivesse respondido.
- Cada tarefa reimplementa a trava `cache.add` + `cache.delete` no erro, com pequenas variações.
- `MessageService.send_*` não levanta em falha (grava `status=failed` e devolve); as tarefas dependem de exceção para o retry.

**Fase 1 (este plano):** canal único + trava única + migração das tarefas. Comportamento preservado.
**Fase 2 (plano separado, precisa do dono):** política por categoria (transacional × marketing × lembrete): opt-out, modo humano, "silenciar notificações" do pedido; ligar ou não o lembrete de PIX do site.
**Fase 3:** motores duplicados (`apps/automation/tasks` sessão × `apps/whatsapp/tasks`; fallback `order._trigger_status_whatsapp_notification`; 3 motores de mensagens agendadas).
**Fase 4:** UI do painel das mensagens automáticas.

## File Structure

- Create `apps/automation/mensageiro/__init__.py` — expõe `enviar_texto`, `enviar_botoes`, `EnvioFalhou`, `reservar`, `liberar`.
- Create `apps/automation/mensageiro/trava.py` — reserva de "só uma vez".
- Create `apps/automation/mensageiro/canal.py` — envio gravado e marcado como automático.
- Modify `apps/whatsapp/services/message_service.py:~771` — `_create_outbound_message` não atualiza `last_agent_message_at` quando `metadata.automatico`.
- Modify `apps/whatsapp/tasks/automation_tasks.py` — `send_payment_reminder` (~102), `send_cart_reminder` (~248), `send_session_cart_reminder` (~687), `send_reengagement_message` (~871) passam pelo canal; `notify_order_status_change` (~531) e `request_feedback` (~635) marcam `automatico`.
- Tests em `apps/automation/tests/test_mensageiro_*.py` e ajustes em `apps/whatsapp/tests/test_lembrete_de_sessao_chega.py`, `test_reengajamento_respeita_saida.py`.

---

### Task 1: Trava única de "só uma vez"

**Files:**
- Create: `apps/automation/mensageiro/__init__.py`, `apps/automation/mensageiro/trava.py`
- Test: `apps/automation/tests/test_mensageiro_trava.py`

**Interfaces:**
- Produces: `reservar(chave: str, segundos: int) -> bool` (True = pode enviar), `liberar(chave: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
from django.core.cache import cache
import pytest
from apps.automation.mensageiro import liberar, reservar

@pytest.fixture(autouse=True)
def _cache():
    cache.clear(); yield; cache.clear()

def test_primeira_reserva_pode_enviar():
    assert reservar('pix:1:first', 3600) is True

def test_segunda_reserva_nao_pode():
    reservar('pix:1:first', 3600)
    assert reservar('pix:1:first', 3600) is False

def test_liberar_permite_tentar_de_novo():
    reservar('pix:1:first', 3600)
    liberar('pix:1:first')
    assert reservar('pix:1:first', 3600) is True
```

- [ ] **Step 2: Run it — expect ImportError**
- [ ] **Step 3: Implement**

```python
# trava.py
"""Reserva de 'só uma vez' das mensagens automáticas.

Cada tarefa reimplementava `cache.add` + `cache.delete` no erro. A regra é uma:
reserva antes de enviar; se nada saiu, libera para a nova tentativa passar;
se saiu, mantém — senão o cliente recebe duas.
"""
from django.core.cache import cache

def reservar(chave: str, segundos: int) -> bool:
    return bool(cache.add(chave, 1, timeout=segundos))

def liberar(chave: str) -> None:
    cache.delete(chave)
```

```python
# __init__.py
from .trava import liberar, reservar  # noqa: F401
```

- [ ] **Step 4: Run — expect PASS**
- [ ] **Step 5: Commit** `feat(mensageiro): trava única de só-uma-vez`

### Task 2: Canal único gravado e marcado como automático

**Files:**
- Create: `apps/automation/mensageiro/canal.py`; Modify `__init__.py`
- Modify: `apps/whatsapp/services/message_service.py` (`_create_outbound_message`)
- Test: `apps/automation/tests/test_mensageiro_canal.py`

**Interfaces:**
- Consumes: `MessageService.send_text_message(account_id, to, text, metadata=)`, `MessageService.send_interactive_buttons(account_id, to, body_text, buttons, metadata=)`.
- Produces: `enviar_texto(conta, telefone: str, texto: str, evento: str) -> Message`, `enviar_botoes(conta, telefone: str, texto: str, botoes: list[dict], evento: str) -> Message`, `class EnvioFalhou(Exception)`.

- [ ] **Step 1: Failing tests** — (a) a mensagem vira `Message` OUTBOUND na conversa com `metadata['automatico'] is True` e `metadata['evento'] == 'pix_reminder'`; (b) `last_agent_message_at` da conversa NÃO muda; (c) Meta devolvendo erro → `EnvioFalhou`. Patch: `apps.whatsapp.services.whatsapp_api_service.WhatsAppAPIService.send_text_message` / `send_interactive_buttons` (`return_value={'messages': [{'id': 'wamid.x'}]}` ou `side_effect=Exception('meta fora')`); conta = `WhatsAppAccount` real.
- [ ] **Step 2: Run — expect ImportError / assert fail**
- [ ] **Step 3: Implement**

```python
# canal.py
"""Canal único das mensagens automáticas.

Seis tarefas chamavam `WhatsAppAPIService` direto: a mensagem saía e não era
gravada (79 enviadas × 1 visível no painel em 30 dias, 19/09). Aqui tudo passa
pelo `MessageService`, que grava na conversa. `automatico=True` impede que o
envio conte como 'a loja respondeu' na Fila humana.
"""
from apps.whatsapp.models import Message
from apps.whatsapp.services.message_service import MessageService


class EnvioFalhou(Exception):
    """O WhatsApp recusou ou não respondeu — a tarefa deve tentar de novo."""


def _meta(evento: str) -> dict:
    return {'automatico': True, 'evento': evento}


def _conferir(mensagem):
    if mensagem is None or getattr(mensagem, 'status', None) == Message.MessageStatus.FAILED:
        raise EnvioFalhou(getattr(mensagem, 'error_message', '') or 'envio falhou')
    return mensagem


def enviar_texto(conta, telefone: str, texto: str, evento: str):
    return _conferir(MessageService().send_text_message(
        account_id=str(conta.id), to=telefone, text=texto, metadata=_meta(evento),
    ))


def enviar_botoes(conta, telefone: str, texto: str, botoes: list, evento: str):
    return _conferir(MessageService().send_interactive_buttons(
        account_id=str(conta.id), to=telefone, body_text=texto, buttons=botoes,
        metadata=_meta(evento),
    ))
```

In `message_service._create_outbound_message`, trocar a atualização de timestamps por:

```python
        if conversation:
            try:
                conversation.last_message_at = timezone.now()
                campos = ['last_message_at', 'updated_at']
                # Automática não é "uma pessoa respondeu" (Fila humana).
                if not meta.get('automatico'):
                    conversation.last_agent_message_at = timezone.now()
                    campos.append('last_agent_message_at')
                conversation.save(update_fields=campos)
            except Exception as e:
                logger.warning(f"Could not update conversation timestamps: {e}")
```

- [ ] **Step 4: Run tests + `apps/whatsapp` + `apps/conversations` — PASS**
- [ ] **Step 5: Commit** `feat(mensageiro): canal único grava a mensagem e marca automática`

### Task 3: Lembrete de PIX pelo canal

**Files:** Modify `automation_tasks.py:send_payment_reminder`; Test `apps/automation/tests/test_mensageiro_lembrete_pix.py`

- [ ] **Step 1: Characterization + new tests** — pedido `payment_status='pending'`, `CompanyProfile` com `AutoMessage` ativo `pix_reminder` (ver `PIX_TEMPLATES`), conta real ligada ao perfil (patch `_get_account_for_profile` devolvendo a conta real). Assert: (a) `Message` gravada com o texto renderizado e `evento='pix_reminder'`; (b) `order.metadata['payment_reminder_first_sent']` preenchido; (c) pedido pago → nada enviado; (d) segunda execução → nada enviado (trava).
- [ ] **Step 2: Run — (a) fails (nada gravado)**
- [ ] **Step 3: Implement** — trocar `cache.add`/`cache.delete` por `reservar`/`liberar` (mesma chave `pix_reminder:{order_id}:{reminder_type}`, 3600 s) e `WhatsAppAPIService(...).send_text_message(...)` por `enviar_texto(account, order.customer_phone, message, evento='pix_reminder')`.
- [ ] **Step 4: Run `apps/whatsapp apps/automation` — PASS**
- [ ] **Step 5: Commit** `refactor(mensageiro): lembrete de PIX grava na conversa`

### Task 4: Lembrete de carrinho do site pelo canal

Igual à Task 3 para `send_cart_reminder` (~248): chave e TTL atuais, `service.send_interactive_buttons(...)` → `enviar_botoes(account, telefone, body, botoes, evento='cart_reminder')`. Teste: carrinho `StoreCart` com item e usuário com telefone; `Message` gravada; `metadata['reminder_<tipo>_sent']` no carrinho; segunda execução não envia. Commit `refactor(mensageiro): lembrete de carrinho do site grava na conversa`.

### Task 5: Lembrete de carrinho do bot pelo canal

`send_session_cart_reminder` (~687): `WhatsAppAPIService(account).send_interactive_buttons(...)` → `enviar_botoes(..., evento='session_cart_reminder')`. Ajustar `apps/whatsapp/tests/test_lembrete_de_sessao_chega.py`: a conta passa a ser `WhatsAppAccount` real (o `MessageService` busca por id); o patch em `WhatsAppAPIService.send_interactive_buttons` continua valendo (o `MessageService` o chama por dentro). As asserções de texto ("Oi, você!") ficam. Commit `refactor(mensageiro): lembrete de carrinho do bot grava na conversa`.

### Task 6: Reengajamento pelo canal

`send_reengagement_message` (~871): trava via `reservar`/`liberar` (chave `reengagement:{store_id}:{phone}`, 86400 s), envio via `enviar_botoes(..., evento='reengagement')`, opt-out mantido. Ajustar `test_reengajamento_respeita_saida.py` para conta real. Commit `refactor(mensageiro): reengajamento grava na conversa`.

### Task 7: Status do pedido e avaliação marcados como automáticos

`notify_order_status_change` (~531) e `request_feedback` (~635) já usam `MessageService`: acrescentar `metadata={'automatico': True, 'evento': <event_type>}` (juntando ao metadata existente, se houver). Teste: cliente esperando na Fila humana continua esperando depois de um aviso de status. Commit `fix(mensageiro): aviso de status não tira o cliente da Fila humana`.

### Task 8: Trava estática contra envio direto

Test `apps/automation/tests/test_mensageiro_sem_envio_direto.py`: lê `apps/whatsapp/tasks/automation_tasks.py` e falha se encontrar `WhatsAppAPIService(` — toda mensagem automática passa pelo canal. Commit `test(mensageiro): trava contra envio direto`.

### Task 9: Verificação e deploy

- [ ] Suíte: `apps/automation apps/whatsapp apps/conversations apps/stores/tests apps/campaigns apps/core` — só as falhas pré-existentes conhecidas.
- [ ] Deploy (constraints) e conferir em produção após 24h: `select metadata->>'evento', count(*) from whatsapp_messages where metadata->>'automatico'='true' group by 1`.
