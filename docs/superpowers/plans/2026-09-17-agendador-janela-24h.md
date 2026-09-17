# Agendador de campanha ciente da janela de 24h — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Campanha de texto livre sai de graça para o máximo de gente: cada
destinatário recebe no horário da campanha ou, se a janela dele fechar antes,
1 hora antes de fechar — nunca entre 21h e 8h, nunca em outro dia.

**Architecture:** Uma função pura (`horario_alvo`) decide o horário de cada
pessoa; uma rodada do Celery Beat roda a cada 60s no dia da campanha, recalcula
esse horário **ao vivo** e envia para quem já chegou a hora, reservando cada
destinatário com um UPDATE condicional (`pending → sending`). Nada é gravado
como "horário previsto" para decidir: o que vale é sempre o cálculo do momento.

**Tech Stack:** Django 4 + DRF, Celery + Beat + Redis (lock), PostgreSQL,
pytest; painel React/Vite + TypeScript + Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-17-agendador-janela-24h-design.md`
(decisões D1–D9). Leia o spec antes da primeira tarefa.

## Global Constraints

- **Fuso é o da loja** (`Store.timezone`, default `America/Sao_Paulo`). O
  container roda em **UTC** — nenhum cálculo de "que horas são" pode usar o fuso
  do servidor. Toda comparação de data/faixa horária é feita no fuso da loja.
- **Faixa de silêncio (D4):** nada sai fora de **[08:00, 21:00]** no fuso da
  loja. 21:00 em ponto ainda vale.
- **Antecipação (D3):** 1 hora antes de a janela fechar.
- **Só no mesmo dia (D5):** alvo em data local diferente da data local da
  campanha → a pessoa fica de fora.
- **Cálculo ao vivo (D6):** `fecha_em` é lido do banco a cada rodada. Nenhum
  horário por pessoa é gravado para decidir envio. `variables['alvo_previsto']`
  existe **só para exibir** na tela.
- **Campanha com template não muda (D7):** todo o fluxo novo vale apenas para
  campanha **sem** `template` (texto livre).
- **Fora da janela é `SKIPPED`, nunca `FAILED`** — inclusive o erro `131047` da
  Meta. Falha inflada esconde falha de verdade.
- **Rodar a suíte:**
  `docker exec -e TEST_DB_HOST=pastita_test_db -e DJANGO_SETTINGS_MODULE=config.settings.test pastita_web /opt/venv/bin/python -m pytest <caminho> -q`
  (o `pastita_web` precisa estar na rede `sdd_test_net`:
  `docker network connect sdd_test_net pastita_web`). Arquivo novo precisa de
  `docker cp` para dentro do container antes de rodar.
- **Painel:** `npm test -- <caminho>` (Vitest) em `/home/graco/WORK/pastita-dash`.
- **Commit por tarefa**, mensagem em português, corpo explicando o *porquê*.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `apps/campaigns/services/janela.py` (modificar) | Regra pura do horário de cada pessoa + leitura dos fechamentos + fuso da campanha |
| `apps/campaigns/services/rodada_da_janela.py` (criar) | O ciclo: calcula, reserva, envia, fecha a campanha |
| `apps/campaigns/models.py` (modificar) | `RecipientStatus.SENDING` |
| `apps/campaigns/migrations/0003_recipient_sending.py` (criar) | Migração do novo status |
| `apps/campaigns/services/campaign_service.py` (modificar) | Marca automática (D1); tirar o recorte do `start_campaign` para campanha marcada |
| `apps/campaigns/tasks/__init__.py` (modificar) | `check_scheduled_campaigns` considera o **dia**; chama a rodada; solta reserva presa |
| `apps/campaigns/api/views.py` (modificar) | Prévia com faixas; detalhe ao vivo da campanha |
| `pastita-dash/src/pages/marketing/whatsapp/linhaDoDia.ts` (criar) | Módulo puro: faixas, marcador "agora", trava 08–21 |
| `pastita-dash/src/components/campanhas/LinhaDoDia.tsx` (criar) | Desenho da linha do tempo (A) + agenda em faixas (C) |
| `pastita-dash/src/pages/marketing/whatsapp/NewWhatsAppCampaignPage.tsx` (modificar) | Modal de agendamento usa a linha do dia e trava o horário |
| `pastita-dash/src/pages/marketing/whatsapp/CampanhaEmAndamentoPage.tsx` (modificar/criar) | A mesma linha, com "agora", enviadas e próxima faixa |

---

### Task 1: A regra pura do horário de cada destinatário

**Files:**
- Modify: `apps/campaigns/services/janela.py`
- Test: `apps/campaigns/tests/test_horario_alvo.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `INICIO_DO_DIA = 8`, `FIM_DO_DIA = 21`, `ANTECIPACAO = timedelta(hours=1)`
  - `horario_alvo(fecha_em: datetime | None, horario_campanha: datetime, fuso: str) -> datetime | None`

- [ ] **Step 1: Escrever o teste que falha**

`apps/campaigns/tests/test_horario_alvo.py`:

```python
"""Quando cada pessoa recebe — a tabela do spec, virada em teste.

A regra: a pessoa recebe no horário da campanha, salvo se a janela dela fechar
antes; aí recebe 1h antes de fechar. Nunca entre 21h e 8h, nunca em outro dia.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.campaigns.services.janela import horario_alvo

SP = 'America/Sao_Paulo'


def sp(ano, mes, dia, hora, minuto=0):
    return datetime(ano, mes, dia, hora, minuto, tzinfo=ZoneInfo(SP))


CAMPANHA = sp(2026, 9, 18, 20)  # sexta, 20h


@pytest.mark.parametrize('ultima_msg, esperado', [
    # fecha 12:00 de hoje → 1h antes (o exemplo do dono)
    (sp(2026, 9, 17, 12), sp(2026, 9, 18, 11)),
    # fecha amanhã 09:00, bem depois das 20h → recebe no horário da campanha
    (sp(2026, 9, 18, 9), CAMPANHA),
    # fecha 20:30 → 19:30
    (sp(2026, 9, 17, 20, 30), sp(2026, 9, 18, 19, 30)),
])
def test_alvo_da_tabela(ultima_msg, esperado):
    assert horario_alvo(ultima_msg + timedelta(hours=24), CAMPANHA, SP) == esperado


def test_quem_nunca_falou_fica_de_fora():
    assert horario_alvo(None, CAMPANHA, SP) is None


def test_janela_ja_fechada_fica_de_fora():
    fecha_em = sp(2026, 9, 15, 20)
    assert horario_alvo(fecha_em, CAMPANHA, SP) is None


def test_alvo_de_madrugada_recua_para_as_21h_da_vespera_e_cai_por_ser_outro_dia():
    """Quem falou ontem às 06:00 teria alvo 05:00 — silêncio.

    Recua para as 21:00 mais recentes ANTES do alvo (ontem), e a regra do
    mesmo dia (D5) derruba: antecipar para ontem não existe.
    """
    fecha_em = sp(2026, 9, 18, 6)
    assert horario_alvo(fecha_em, CAMPANHA, SP) is None


def test_campanha_em_outro_dia_nao_antecipa_ninguem():
    """D5: sem isso, agendar para depois de amanhã antecipava a lista inteira."""
    campanha = sp(2026, 9, 20, 20)
    fecha_em = sp(2026, 9, 18, 12)
    assert horario_alvo(fecha_em, campanha, SP) is None


def test_as_21h_em_ponto_ainda_vale():
    fecha_em = sp(2026, 9, 18, 22)
    campanha = sp(2026, 9, 18, 21)
    assert horario_alvo(fecha_em, campanha, SP) == campanha


def test_a_conta_e_no_fuso_da_loja_nao_no_do_servidor():
    """O container roda em UTC. 23:30 UTC é 20:30 em SP — dentro da faixa.

    Se a faixa fosse medida em UTC, esta campanha seria empurrada para as 21h
    UTC (18h em SP) e sairia três horas antes do que o dono escolheu.
    """
    campanha = datetime(2026, 9, 18, 23, 30, tzinfo=ZoneInfo('UTC'))
    fecha_em = campanha + timedelta(hours=5)
    assert horario_alvo(fecha_em, campanha, SP) == campanha
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
docker cp apps/campaigns/tests/test_horario_alvo.py pastita_web:/app/apps/campaigns/tests/
docker exec -e TEST_DB_HOST=pastita_test_db -e DJANGO_SETTINGS_MODULE=config.settings.test \
  pastita_web /opt/venv/bin/python -m pytest apps/campaigns/tests/test_horario_alvo.py -q
```
Esperado: `ImportError: cannot import name 'horario_alvo'`.

- [ ] **Step 3: Implementar**

Acrescentar em `apps/campaigns/services/janela.py`:

```python
from datetime import time
from zoneinfo import ZoneInfo

#: A faixa em que a loja pode falar. Fora dela, ninguém recebe (D4): promoção
#: às 23h não é lembrete, é incômodo — e o cliente que bloqueia some para sempre.
INICIO_DO_DIA = 8
FIM_DO_DIA = 21
#: Quanto antes de a janela fechar a pessoa é antecipada (D3).
ANTECIPACAO = timedelta(hours=1)


def horario_alvo(fecha_em, horario_campanha, fuso: str):
    """Quando ESTA pessoa recebe — ou `None` se não dá para mandar de graça.

    Regra, na ordem (spec, seção 3):
      1. sem janela (nunca falou) → fora;
      2. alvo = min(horário da campanha, fecha_em − 1h);
      3. alvo no silêncio → recua para as 21:00 mais recentes ANTES dele;
      4. alvo em outro dia (local) que o da campanha → fora (D5);
      5. alvo já depois do fechamento → fora.
    """
    if fecha_em is None:
        return None

    zona = ZoneInfo(fuso or 'America/Sao_Paulo')
    alvo = min(horario_campanha, fecha_em - ANTECIPACAO)

    local = alvo.astimezone(zona)
    if local.time() < time(INICIO_DO_DIA) or local.time() > time(FIM_DO_DIA):
        # As 21:00 mais recentes ANTES do alvo: 22:30 → 21:00 do mesmo dia;
        # 05:00 → 21:00 da véspera.
        fim = local.replace(hour=FIM_DO_DIA, minute=0, second=0, microsecond=0)
        if fim > local:
            fim -= timedelta(days=1)
        alvo = fim.astimezone(alvo.tzinfo)

    if alvo.astimezone(zona).date() != horario_campanha.astimezone(zona).date():
        return None
    if alvo >= fecha_em:
        return None
    return alvo
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do passo 2. Esperado: todos verdes.

- [ ] **Step 5: Sanidade — reverter e confirmar que o teste pega**

Troque `zona = ZoneInfo(fuso ...)` por `zona = ZoneInfo('UTC')`, rode:
`test_a_conta_e_no_fuso_da_loja_nao_no_do_servidor` deve **falhar**. Desfaça.

- [ ] **Step 6: Commit**

```bash
git add apps/campaigns/services/janela.py apps/campaigns/tests/test_horario_alvo.py
git commit -m "feat(campanha): regra do horário de cada destinatário na janela de 24h"
```

---

### Task 2: Ler os fechamentos e o fuso da campanha

**Files:**
- Modify: `apps/campaigns/services/janela.py`
- Test: `apps/campaigns/tests/test_fechamentos_por_chave.py`

**Interfaces:**
- Consumes: `chave_do_telefone` (de `.contatos`), `JANELA_HORAS`.
- Produces:
  - `fechamentos_por_chave(account_ids) -> dict[str, datetime]`
  - `fuso_da_campanha(campaign) -> str`

- [ ] **Step 1: Escrever o teste que falha**

`apps/campaigns/tests/test_fechamentos_por_chave.py` — siga o setup de
`apps/campaigns/tests/test_janela_de_24h.py` (cria `WhatsAppAccount` e
`Conversation`). Testes:

```python
def test_devolve_quando_a_janela_de_cada_telefone_fecha(self):
    falou = timezone.now() - timedelta(hours=3)
    self._conversa('5511999990000', falou)

    mapa = fechamentos_por_chave([self.account.id])

    assert mapa[chave_do_telefone('5511999990000')] == falou + timedelta(hours=24)

def test_quem_nunca_falou_nao_entra_no_mapa(self):
    self._conversa('5511999990001', None)
    assert fechamentos_por_chave([self.account.id]) == {}

def test_a_conversa_mais_recente_vence_para_o_mesmo_telefone(self):
    """O nono dígito faz o mesmo cliente virar duas conversas. A janela é a
    da mensagem MAIS NOVA — pegar a antiga descartaria quem está dentro."""
    antiga = timezone.now() - timedelta(hours=20)
    nova = timezone.now() - timedelta(hours=1)
    self._conversa('551199990002', antiga)
    self._conversa('5511999990002', nova)

    mapa = fechamentos_por_chave([self.account.id])

    assert mapa[chave_do_telefone('5511999990002')] == nova + timedelta(hours=24)

def test_fuso_vem_da_loja_da_conta(self):
    self.store.timezone = 'America/Manaus'
    self.store.save(update_fields=['timezone'])
    assert fuso_da_campanha(self.campaign) == 'America/Manaus'

def test_sem_loja_cai_no_fuso_do_settings(self):
    assert fuso_da_campanha(self.campanha_orfa) == settings.TIME_ZONE
```

- [ ] **Step 2: Rodar e ver falhar** (`ImportError`).

- [ ] **Step 3: Implementar**

```python
def fechamentos_por_chave(account_ids) -> dict:
    """{chave do telefone: quando a janela fecha}. Só quem já falou entra.

    Mesma chave canônica do recorte e da dedupe: o wa_id chega sem o nono
    dígito e o pedido tem com ele. Duas conversas do mesmo cliente → vale a
    mensagem MAIS NOVA, senão descartaríamos quem está dentro da janela.
    """
    from apps.conversations.models import Conversation

    mapa = {}
    linhas = (
        Conversation.objects
        .filter(account_id__in=list(account_ids))
        .exclude(last_customer_message_at=None)
        .values_list('phone_number', 'last_customer_message_at')
    )
    for telefone, ultima in linhas:
        chave = chave_do_telefone(telefone)
        if not chave:
            continue
        fecha = ultima + timedelta(hours=JANELA_HORAS)
        if fecha > mapa.get(chave, fecha - timedelta(seconds=1)):
            mapa[chave] = fecha
    return mapa


def fuso_da_campanha(campaign) -> str:
    """O fuso da LOJA dona da conta — o container roda em UTC.

    A ligação loja↔conta tem três caminhos (FK direta, perfil de automação e
    integração legada). Aqui só os dois primeiros existem no sentido inverso;
    sem loja, cai no fuso do settings.
    """
    from django.conf import settings
    from apps.stores.models import Store

    loja = (
        Store.objects.filter(whatsapp_account_id=campaign.account_id).first()
        or Store.objects.filter(automation_profile__account_id=campaign.account_id).first()
    )
    return getattr(loja, 'timezone', None) or settings.TIME_ZONE
```

- [ ] **Step 4: Rodar e ver passar.**

- [ ] **Step 5: Commit**

```bash
git add apps/campaigns/services/janela.py apps/campaigns/tests/test_fechamentos_por_chave.py
git commit -m "feat(campanha): fechamentos por telefone e fuso da loja para a rodada da janela"
```

---

### Task 3: Marca automática — texto livre é sempre "só janela aberta" (D1)

**Files:**
- Modify: `apps/campaigns/services/campaign_service.py` (`create_campaign`, `update_campaign`)
- Test: `apps/campaigns/tests/test_marca_automatica_da_janela.py`

**Interfaces:**
- Consumes: `janela.MARCA` (`'somente_janela_aberta'`).
- Produces: toda campanha sem `template` nasce com
  `audience_filters['somente_janela_aberta'] = True`.

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_campanha_de_texto_livre_nasce_marcada(self):
    campanha = CampaignService().create_campaign(
        account_id=str(self.account.id), name='Promo', message_content={'text': 'oi'},
    )
    assert campanha.audience_filters[MARCA] is True

def test_campanha_com_template_nao_e_marcada(self):
    campanha = CampaignService().create_campaign(
        account_id=str(self.account.id), name='Promo', template_id=str(self.template.id),
    )
    assert MARCA not in campanha.audience_filters

def test_filtros_que_o_dono_escolheu_continuam_valendo(self):
    campanha = CampaignService().create_campaign(
        account_id=str(self.account.id), name='Promo',
        message_content={'text': 'oi'}, audience_filters={'bairro': 'Centro'},
    )
    assert campanha.audience_filters['bairro'] == 'Centro'
    assert campanha.audience_filters[MARCA] is True

def test_tirar_o_template_na_edicao_marca_a_campanha(self):
    campanha = CampaignService().create_campaign(
        account_id=str(self.account.id), name='Promo', template_id=str(self.template.id),
    )
    CampaignService().update_campaign(str(campanha.id), template_id=None)
    campanha.refresh_from_db()
    assert campanha.audience_filters[MARCA] is True
```

- [ ] **Step 2: Rodar e ver falhar** (`KeyError: 'somente_janela_aberta'`).

- [ ] **Step 3: Implementar**

Em `create_campaign`, antes do `Campaign.objects.create`:

```python
        # D1: texto livre SÓ existe dentro da janela de 24h — a Meta recusa
        # fora dela (131047). Marcar é decisão do sistema, não caixinha de
        # tela: 0 de 8 campanhas em produção tinham a marca, e todas saíram
        # para gente fora da janela.
        from .janela import MARCA
        audience_filters = dict(audience_filters or {})
        if not template_id:
            audience_filters[MARCA] = True
```

Em `update_campaign`, depois de aplicar os `kwargs` e antes do `save`, recalcule
a marca pelo `campaign.template_id` final (marca quando ficou sem template;
remove a marca quando ganhou template).

- [ ] **Step 4: Rodar e ver passar.**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(campanha): campanha de texto livre nasce marcada como 'só janela aberta'"
```

---

### Task 4: Status `SENDING` e a reserva sem lock longo

**Files:**
- Modify: `apps/campaigns/models.py:125-133` (`RecipientStatus`)
- Create: `apps/campaigns/migrations/0003_recipient_sending.py`
- Create: `apps/campaigns/services/rodada_da_janela.py`
- Test: `apps/campaigns/tests/test_reserva_de_destinatario.py`

**Interfaces:**
- Consumes: `CampaignRecipient`.
- Produces:
  - `CampaignRecipient.RecipientStatus.SENDING = 'sending'`
  - `reservar(recipient_id) -> bool` (True = esta rodada é a dona do envio)
  - `liberar_reservas_presas(minutos=10) -> int`

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_reserva_devolve_true_uma_vez_so(self):
    assert reservar(self.destinatario.id) is True
    assert reservar(self.destinatario.id) is False

def test_duas_rodadas_simultaneas_so_uma_envia(self):
    """O teste real da corrida: dois threads no mesmo destinatário."""
    resultados = []
    threads = [Thread(target=lambda: resultados.append(reservar(self.destinatario.id)))
               for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(resultados) == [False, True]

def test_reserva_presa_volta_para_pendente_depois_de_10_min(self):
    """Worker morto no meio do envio não pode sequestrar o destinatário."""
    CampaignRecipient.objects.filter(id=self.destinatario.id).update(
        status='sending', updated_at=timezone.now() - timedelta(minutes=11),
    )
    assert liberar_reservas_presas() == 1
    self.destinatario.refresh_from_db()
    assert self.destinatario.status == 'pending'

def test_reserva_recente_nao_e_liberada(self):
    CampaignRecipient.objects.filter(id=self.destinatario.id).update(status='sending')
    assert liberar_reservas_presas() == 0
```

O teste de corrida precisa de banco real por thread: use
`TransactionTestCase` e feche a conexão em cada thread
(`django.db.connection.close()` no fim do alvo).

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar**

`models.py`, em `RecipientStatus`, depois de `PENDING`:

```python
        #: Reservado por uma rodada, ainda não enviado. Existe para que duas
        #: rodadas simultâneas não mandem a mesma mensagem duas vezes.
        SENDING = 'sending', 'Sending'
```

Migração `0003_recipient_sending.py`: `AlterField` de `status` com as novas
`choices` (não muda dado nenhum — é só o vocabulário do campo).

`apps/campaigns/services/rodada_da_janela.py`:

```python
def reservar(recipient_id) -> bool:
    """Pega o destinatário para esta rodada. True = pode enviar.

    UPDATE condicional, não SELECT+save: entre ler e gravar cabe outra rodada,
    e o cliente receberia a mesma promoção duas vezes.
    """
    from apps.campaigns.models import CampaignRecipient

    linhas = CampaignRecipient.objects.filter(
        id=recipient_id, status=CampaignRecipient.RecipientStatus.PENDING,
    ).update(
        status=CampaignRecipient.RecipientStatus.SENDING,
        updated_at=timezone.now(),
    )
    return linhas == 1


def liberar_reservas_presas(minutos: int = 10) -> int:
    """`sending` velho = worker morreu no meio. Volta para a fila."""
    from apps.campaigns.models import CampaignRecipient

    return CampaignRecipient.objects.filter(
        status=CampaignRecipient.RecipientStatus.SENDING,
        updated_at__lt=timezone.now() - timedelta(minutes=minutos),
    ).update(status=CampaignRecipient.RecipientStatus.PENDING)
```

Atenção: `updated_at` é `auto_now`. Use `.update()` (que **não** dispara
`auto_now`) passando o valor à mão, como acima.

- [ ] **Step 4: Rodar e ver passar.**

- [ ] **Step 5: Aplicar a migração**

```bash
docker exec pastita_web /opt/venv/bin/python manage.py migrate campaigns
```

- [ ] **Step 6: Commit**

```bash
git add apps/campaigns/models.py apps/campaigns/migrations/0003_recipient_sending.py \
        apps/campaigns/services/rodada_da_janela.py apps/campaigns/tests/test_reserva_de_destinatario.py
git commit -m "feat(campanha): reserva condicional de destinatário (status sending)"
```

---

### Task 5: A rodada — quem recebe agora, quem espera, quem fica de fora

**Files:**
- Modify: `apps/campaigns/services/rodada_da_janela.py`
- Test: `apps/campaigns/tests/test_rodada_da_janela.py`

**Interfaces:**
- Consumes: `horario_alvo`, `fechamentos_por_chave`, `fuso_da_campanha`,
  `reservar`, `CampaignService.process_campaign_batch` (não usado aqui — o envio
  é por destinatário), `MessageService`.
- Produces:
  `processar_rodada_da_janela(campaign, agora=None) -> dict` com as chaves
  `enviados`, `aguardando`, `pulados`, `concluida`.

- [ ] **Step 1: Escrever o teste que falha**

```python
"""O dia inteiro da campanha, com o relógio na mão.

Cada rodada é uma foto: recalcula o alvo de cada pendente e envia só quem já
chegou a hora. O teste anda o relógio de hora em hora e confere que ninguém
recebe duas vezes e que ninguém recebe fora da faixa.
"""

def test_quem_tem_janela_larga_so_recebe_no_horario_da_campanha(self):
    # cliente falou hoje 09:00; campanha 20:00; janela fecha amanhã 09:00
    with freeze(self.dia_as(11)):
        assert processar_rodada_da_janela(self.campanha)['enviados'] == 0
    with freeze(self.dia_as(20)):
        assert processar_rodada_da_janela(self.campanha)['enviados'] == 1

def test_quem_fecharia_antes_e_antecipado_uma_hora(self):
    # falou ontem 12:00 → fecha hoje 12:00 → alvo 11:00
    with freeze(self.dia_as(11)):
        assert processar_rodada_da_janela(self.campanha)['enviados'] == 1

def test_ninguem_recebe_duas_vezes_ao_longo_do_dia(self):
    for hora in range(8, 22):
        with freeze(self.dia_as(hora)):
            processar_rodada_da_janela(self.campanha)
    assert self.destinatario_enviados() == 1

def test_quem_nao_cabe_na_janela_vira_skipped_e_nao_failed(self):
    with freeze(self.dia_as(21)):
        resultado = processar_rodada_da_janela(self.campanha)
    assert resultado['pulados'] == 1
    assert self.recipient().status == 'skipped'
    assert self.recipient().error_code == 'fora_da_janela'

def test_campanha_fecha_quando_passou_o_horario_e_nao_ha_pendente(self):
    with freeze(self.dia_as(21)):
        resultado = processar_rodada_da_janela(self.campanha)
    self.campanha.refresh_from_db()
    assert resultado['concluida'] is True
    assert self.campanha.status == 'completed'

def test_campanha_pausada_nao_envia_nada(self):
    self.campanha.status = 'paused'; self.campanha.save()
    with freeze(self.dia_as(20)):
        assert processar_rodada_da_janela(self.campanha)['enviados'] == 0

def test_131047_vira_skipped(self):
    """A Meta ainda pode recusar na corrida entre o cálculo e o envio."""
    with mock_envio_falhando(codigo='131047'), freeze(self.dia_as(20)):
        processar_rodada_da_janela(self.campanha)
    assert self.recipient().status == 'skipped'
    assert self.recipient().error_code == '131047'

def test_respeita_o_teto_de_mensagens_por_minuto(self):
    self.campanha.messages_per_minute = 2; self.campanha.save()
    com_10_pendentes(self)
    with freeze(self.dia_as(20)):
        assert processar_rodada_da_janela(self.campanha)['enviados'] == 2

def test_opt_out_continua_valendo(self):
    """Quem pediu para sair não recebe, nem antecipado."""
    pedir_para_sair(self.telefone)
    with freeze(self.dia_as(20)):
        assert processar_rodada_da_janela(self.campanha)['enviados'] == 0
```

Use `django.test.utils` + `unittest.mock.patch('django.utils.timezone.now')`
(ou `time_machine`, se já estiver no ambiente) para congelar o relógio; o envio
é mockado em `apps.whatsapp.services.MessageService.send_text_message`.

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar**

```python
def processar_rodada_da_janela(campaign, agora=None) -> dict:
    """Uma foto do momento: envia para quem já chegou a hora.

    Nada é agendado por pessoa — o alvo é recalculado a cada rodada porque a
    janela se move: o cliente que responder ao bot às 15h renova a dele e passa
    a caber no horário da campanha.
    """
    from apps.campaigns.models import Campaign, CampaignRecipient
    from apps.campaigns.services.contatos import chave_do_telefone
    from apps.campaigns.services.janela import (
        fechamentos_por_chave, fuso_da_campanha, horario_alvo,
    )
    from apps.campaigns.services.optout import chaves_bloqueadas
    from apps.whatsapp.tasks import acquire_lock, release_lock

    agora = agora or timezone.now()
    if campaign.status not in (Campaign.CampaignStatus.SCHEDULED,
                               Campaign.CampaignStatus.RUNNING):
        return {'enviados': 0, 'aguardando': 0, 'pulados': 0, 'concluida': False}

    if not acquire_lock(f'campanha:{campaign.id}', timeout=120):
        return {'enviados': 0, 'aguardando': 0, 'pulados': 0, 'concluida': False}
    try:
        fuso = fuso_da_campanha(campaign)
        fechamentos = fechamentos_por_chave([campaign.account_id])
        bloqueadas = chaves_bloqueadas(campaign.account)
        teto = max(1, campaign.messages_per_minute or 60)

        enviados = aguardando = pulados = 0
        pendentes = campaign.recipients.filter(
            status=CampaignRecipient.RecipientStatus.PENDING,
        )
        for destinatario in pendentes:
            chave = chave_do_telefone(destinatario.phone_number)
            if chave in bloqueadas:
                _pular(destinatario, 'optout')
                pulados += 1
                continue

            alvo = horario_alvo(fechamentos.get(chave), campaign.scheduled_at, fuso)
            if alvo is None:
                # Só desiste depois que o horário da campanha passou: até lá a
                # pessoa ainda pode responder à loja e reabrir a janela dela.
                if agora >= campaign.scheduled_at:
                    _pular(destinatario, 'fora_da_janela')
                    pulados += 1
                else:
                    aguardando += 1
                continue

            if alvo > agora:
                aguardando += 1
                continue

            if enviados >= teto:
                aguardando += 1
                continue

            if not reservar(destinatario.id):
                continue
            if _enviar(campaign, destinatario):
                enviados += 1
            else:
                pulados += 1

        if enviados and campaign.status != Campaign.CampaignStatus.RUNNING:
            campaign.status = Campaign.CampaignStatus.RUNNING
            campaign.started_at = campaign.started_at or agora
            campaign.save(update_fields=['status', 'started_at', 'updated_at'])

        concluida = agora >= campaign.scheduled_at and aguardando == 0 and not (
            campaign.recipients.filter(
                status=CampaignRecipient.RecipientStatus.SENDING).exists()
        )
        if concluida and campaign.status == Campaign.CampaignStatus.RUNNING:
            campaign.status = Campaign.CampaignStatus.COMPLETED
            campaign.completed_at = agora
            campaign.save(update_fields=['status', 'completed_at', 'updated_at'])

        return {'enviados': enviados, 'aguardando': aguardando,
                'pulados': pulados, 'concluida': concluida}
    finally:
        release_lock(f'campanha:{campaign.id}')
```

`_pular(destinatario, codigo)` grava `status='skipped'` + `error_code=codigo`.
`_enviar(campaign, destinatario)` reusa o trecho de envio de texto/mídia de
`CampaignService.process_campaign_batch` (extraia-o para um método
`_enviar_para(campaign, recipient)` no serviço e chame-o dos dois lugares — não
duplique o corpo), traduz `131047` para `skipped` e incrementa
`messages_sent` / `messages_failed` com `update_fields` (a armadilha dos recibos
concorrentes, ver comentário existente em `campaign_service.py`).

- [ ] **Step 4: Rodar e ver passar.**

- [ ] **Step 5: Sanidade — reverter**

Troque `if alvo > agora: aguardando += 1; continue` por `pass` e confirme que
`test_quem_tem_janela_larga_so_recebe_no_horario_da_campanha` falha. Desfaça.

- [ ] **Step 6: Commit**

```bash
git add apps/campaigns/services/rodada_da_janela.py apps/campaigns/services/campaign_service.py \
        apps/campaigns/tests/test_rodada_da_janela.py
git commit -m "feat(campanha): rodada que envia cada pessoa no horário dela dentro da janela"
```

---

### Task 6: Ligar a rodada no Beat e tirar o recorte do start_campaign

**Files:**
- Modify: `apps/campaigns/tasks/__init__.py:64-80` (`check_scheduled_campaigns`)
- Modify: `apps/campaigns/services/campaign_service.py:119-145` (`start_campaign`)
- Test: `apps/campaigns/tests/test_beat_da_janela.py`

**Interfaces:**
- Consumes: `processar_rodada_da_janela`, `liberar_reservas_presas`, `MARCA`.
- Produces: `check_scheduled_campaigns` roda a rodada para campanha marcada
  cujo `scheduled_at` é **hoje** no fuso da loja.

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_campanha_marcada_roda_no_dia_mesmo_antes_do_horario(self):
    """Às 11h a campanha das 20h já precisa rodar: é quando o antecipado sai."""
    with freeze(self.dia_as(11)):
        check_scheduled_campaigns()
    assert self.rodada_foi_chamada_para(self.campanha)

def test_campanha_marcada_de_amanha_nao_roda_hoje(self):
    with freeze(self.dia_as(11)):
        check_scheduled_campaigns()
    assert not self.rodada_foi_chamada_para(self.campanha_de_amanha)

def test_campanha_com_template_segue_o_caminho_antigo(self):
    """D7: template vira RUNNING no horário e cai no process_campaign."""
    with freeze(self.dia_as(20)):
        check_scheduled_campaigns()
    self.campanha_template.refresh_from_db()
    assert self.campanha_template.status == 'running'
    assert self.process_campaign_foi_chamado

def test_reservas_presas_sao_liberadas_a_cada_passagem(self):
    prender_reserva(self.destinatario, minutos=11)
    check_scheduled_campaigns()
    assert self.recipient().status == 'pending'

def test_start_campaign_nao_recorta_campanha_marcada(self):
    """O recorte descartava quem só caberia mais tarde — agora é por pessoa."""
    CampaignService().start_campaign(str(self.campanha.id))
    assert self.recipient().status == 'pending'
```

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar**

`check_scheduled_campaigns`:

```python
@shared_task
def check_scheduled_campaigns():
    """Duas famílias de campanha, dois caminhos.

    Template: continua virando RUNNING no horário marcado.
    Texto livre (marcada): roda o DIA INTEIRO, porque o horário de cada pessoa
    pode ser antes do horário da campanha — é assim que quem fecharia a janela
    às 12h recebe às 11h em vez de ser descartado.
    """
    from django.utils import timezone
    from ..models import Campaign
    from ..services.janela import MARCA, fuso_da_campanha
    from ..services.rodada_da_janela import (
        liberar_reservas_presas, processar_rodada_da_janela,
    )
    from zoneinfo import ZoneInfo

    liberar_reservas_presas()
    agora = timezone.now()

    marcadas = Campaign.objects.filter(
        status__in=[Campaign.CampaignStatus.SCHEDULED, Campaign.CampaignStatus.RUNNING],
        is_active=True,
        audience_filters__somente_janela_aberta=True,
    ).exclude(scheduled_at=None)
    for campanha in marcadas:
        zona = ZoneInfo(fuso_da_campanha(campanha))
        if campanha.scheduled_at.astimezone(zona).date() != agora.astimezone(zona).date():
            continue
        processar_rodada_da_janela(campanha, agora=agora)

    antigas = Campaign.objects.filter(
        status=Campaign.CampaignStatus.SCHEDULED,
        scheduled_at__lte=agora,
        is_active=True,
    ).exclude(audience_filters__somente_janela_aberta=True)
    for campaign in antigas:
        campaign.status = Campaign.CampaignStatus.RUNNING
        campaign.started_at = agora
        campaign.save()
        process_campaign.delay(str(campaign.id))
```

`start_campaign`: chame `recortar_para_a_janela` **apenas** quando a campanha
não for marcada… na prática, campanha marcada nunca deve passar pelo recorte —
troque o bloco por:

```python
        from .janela import MARCA, recortar_para_a_janela
        marcada = bool((campaign.audience_filters or {}).get(MARCA))
        if marcada:
            # A decisão passou a ser POR PESSOA, na hora dela (rodada da
            # janela). Recortar aqui jogaria fora quem só caberia mais tarde.
            from ..tasks import check_scheduled_campaigns  # noqa: F401
        else:
            recorte = recortar_para_a_janela(campaign)
            ...  # bloco atual, intocado
```

Campanha marcada iniciada "agora" deve receber `scheduled_at = timezone.now()`
se estiver vazio, para a rodada ter um horário de referência.

- [ ] **Step 4: Rodar e ver passar** (inclua
  `apps/campaigns/tests/test_janela_de_24h.py` na mesma execução — ele cobre o
  recorte antigo e **não pode quebrar** para campanha com template).

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(campanha): Beat roda a janela o dia inteiro; start_campaign não recorta mais a marcada"
```

---

### Task 7: Prévia e detalhe ao vivo — os números que a tela mostra

**Files:**
- Modify: `apps/campaigns/services/janela.py` (`resumo_da_janela`)
- Modify: `apps/campaigns/api/views.py:815-855` (`JanelaDaAudienciaView`) e
  `CampaignViewSet` (nova action `faixas`)
- Test: `apps/campaigns/tests/test_previa_em_faixas.py`

**Interfaces:**
- Consumes: `horario_alvo`, `fechamentos_por_chave`, `fuso_da_campanha`.
- Produces:
  - `resumo_da_janela(account_ids, em=None, fuso=None)` passa a devolver também
    `no_horario`, `antecipados`, `de_fora`, `primeiro_antecipado_em`,
    `faixas: [{'hora': 11, 'quantidade': 3}]`
  - `GET /campaigns/{id}/faixas/` → `{faixas: [{hora, enviadas, aguardando}],
    proxima_faixa, mudaram_de_horario: [{nome, telefone, de, para}]}`

- [ ] **Step 1: Escrever o teste que falha**

```python
def test_previa_separa_quem_recebe_no_horario_de_quem_e_antecipado(self):
    resumo = resumo_da_janela([self.account.id], em=self.dia_as(20), fuso='America/Sao_Paulo')
    assert resumo['no_horario'] == 2
    assert resumo['antecipados'] == 1
    assert resumo['de_fora'] == 1

def test_previa_devolve_as_faixas_do_dia(self):
    resumo = resumo_da_janela([self.account.id], em=self.dia_as(20), fuso='America/Sao_Paulo')
    assert {'hora': 11, 'quantidade': 1} in resumo['faixas']
    assert resumo['primeiro_antecipado_em'].hour == 11

def test_a_previa_bate_com_o_que_a_rodada_faria(self):
    """Prévia e envio usam a MESMA conta — número de tela que mente é pior
    que número nenhum."""
    previa = resumo_da_janela([self.account.id], em=self.dia_as(20), fuso=self.fuso)
    with freeze(self.dia_as(23)):   # depois de tudo
        rodar_o_dia_inteiro(self.campanha)
    assert enviados(self.campanha) == previa['no_horario'] + previa['antecipados']

def test_detalhe_mostra_quem_mudou_de_horario(self):
    """Quem respondeu à loja depois do agendamento renovou a janela e agora
    recebe no horário cheio — a tela precisa dizer isso."""
    ...
    assert resposta.data['mudaram_de_horario'][0]['para'] == '20:00'
```

- [ ] **Step 2: Rodar e ver falhar** (`KeyError: 'no_horario'`).

- [ ] **Step 3: Implementar**

`resumo_da_janela` passa a montar, para cada chave do
`fechamentos_por_chave`, o `horario_alvo(fecha_em, em, fuso)` e a contar:
`no_horario` (alvo == `em`), `antecipados` (alvo < `em`), `de_fora` (None).
As faixas são `Counter` por hora local do alvo, ordenadas.

A action nova no `CampaignViewSet` reusa a mesma função e cruza com os
`CampaignRecipient` já `SENT`/`SKIPPED` para devolver `enviadas`/`aguardando`
por faixa. `mudaram_de_horario` compara o alvo de agora com
`recipient.variables.get('alvo_previsto')` (gravado no agendamento **apenas**
para exibição — nunca lido para decidir envio).

- [ ] **Step 4: Rodar e ver passar.**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(campanha): prévia e detalhe da campanha em faixas de horário"
```

---

### Task 8: Painel — o módulo puro da linha do dia

**Files:**
- Create: `pastita-dash/src/pages/marketing/whatsapp/linhaDoDia.ts`
- Test: `pastita-dash/src/pages/marketing/whatsapp/__tests__/linhaDoDia.test.ts`

**Interfaces:**
- Produces:
  - `INICIO = 8`, `FIM = 21`
  - `montarLinhaDoDia({ faixas, horarioDaCampanha, agora }) -> { horas: {hora, quantidade, enviadas, passou, eAgora, eDaCampanha}[], totalAntecipado, totalNoHorario }`
  - `horarioPermitido(valorDoCampo: string) -> { ok: boolean; motivo: string }`
  - `resumoDaAgenda(linha) -> string`

- [ ] **Step 1: Escrever o teste que falha**

```typescript
describe('linha do dia', () => {
  it('marca a faixa do horário da campanha', () => {
    const linha = montarLinhaDoDia({
      faixas: [{ hora: 11, quantidade: 3 }, { hora: 20, quantidade: 12 }],
      horarioDaCampanha: '2026-09-18T20:00', agora: '2026-09-18T11:30',
    });
    expect(linha.horas.find((h) => h.hora === 20)?.eDaCampanha).toBe(true);
  });

  it('marca como passada só a faixa anterior a agora', () => {
    const linha = montarLinhaDoDia({ ...base, agora: '2026-09-18T11:30' });
    expect(linha.horas.find((h) => h.hora === 11)?.passou).toBe(true);
    expect(linha.horas.find((h) => h.hora === 12)?.passou).toBe(false);
  });

  it('separa antecipados de quem recebe no horário', () => {
    const linha = montarLinhaDoDia({ ...base });
    expect(linha.totalAntecipado).toBe(3);
    expect(linha.totalNoHorario).toBe(12);
  });

  it('recusa horário fora de 8h–21h', () => {
    expect(horarioPermitido('2026-09-18T22:30').ok).toBe(false);
    expect(horarioPermitido('2026-09-18T22:30').motivo)
      .toMatch(/entre 8h e 21h/);
  });

  it('aceita 21:00 em ponto', () => {
    expect(horarioPermitido('2026-09-18T21:00').ok).toBe(true);
  });

  it('campo pela metade não vira erro na cara de quem está digitando', () => {
    expect(horarioPermitido('2026-09-').ok).toBe(true);
  });

  it('o resumo diz os dois números, não só o bom', () => {
    expect(resumoDaAgenda(montarLinhaDoDia({ ...base })))
      .toBe('12 recebem às 20h · 3 antes, para não perder a janela');
  });
});
```

- [ ] **Step 2: `npm test -- linhaDoDia` — ver falhar** (módulo não existe).

- [ ] **Step 3: Implementar** o módulo com essas funções puras. Sem React, sem
  chamada de API: é o pedaço que os dois lugares (agendar e rodando) usam.

- [ ] **Step 4: `npm test -- linhaDoDia` — ver passar.**

- [ ] **Step 5: Commit**

```bash
git add src/pages/marketing/whatsapp/linhaDoDia.ts src/pages/marketing/whatsapp/__tests__/linhaDoDia.test.ts
git commit -m "feat(campanha): módulo puro da linha do dia (faixas, agora, trava 8h-21h)"
```

---

### Task 9: Painel — a linha do tempo no modal de agendamento (A + C)

**Files:**
- Create: `pastita-dash/src/components/campanhas/LinhaDoDia.tsx`
- Modify: `pastita-dash/src/pages/marketing/whatsapp/NewWhatsAppCampaignPage.tsx:1233-1268`
- Modify: `pastita-dash/src/services/campaigns.ts:310-325` (`getJanelaDaAudiencia` devolve as faixas)
- Test: `pastita-dash/src/components/campanhas/__tests__/LinhaDoDia.test.tsx`

**Interfaces:**
- Consumes: `montarLinhaDoDia`, `horarioPermitido`, `resumoDaAgenda`.
- Produces: `<LinhaDoDia faixas horarioDaCampanha agora modo="agendar" | "rodando" onEscolherFaixa />`

Mockups aprovados: `pastita-dash/.superpowers/brainstorm/*/content/agendamento-combinado-v2.html`
(decisão D8: linha do tempo do dia **+** agenda em faixas, nos dois momentos).

- [ ] **Step 1: Escrever o teste que falha**

```tsx
it('desenha uma coluna por hora entre 8h e 21h', () => {
  render(<LinhaDoDia {...base} />);
  expect(screen.getAllByRole('listitem')).toHaveLength(14);
});

it('a faixa do horário escolhido aparece destacada e nomeada', () => {
  render(<LinhaDoDia {...base} />);
  expect(screen.getByRole('listitem', { name: /20h · 12 pessoas · horário da campanha/i }))
    .toBeInTheDocument();
});

it('mostra quantos são antecipados, sem esconder o número', () => {
  render(<LinhaDoDia {...base} />);
  expect(screen.getByText(/3 antes, para não perder a janela/i)).toBeInTheDocument();
});

it('clicar numa faixa abre quem está nela', async () => {
  const aoEscolher = vi.fn();
  render(<LinhaDoDia {...base} onEscolherFaixa={aoEscolher} />);
  await userEvent.click(screen.getByRole('button', { name: /11h/ }));
  expect(aoEscolher).toHaveBeenCalledWith(11);
});

it('no modal, agendar às 22h é recusado com o motivo na tela', async () => {
  render(<NewWhatsAppCampaignPage />);
  ...
  await userEvent.type(campo, '2026-09-18T22:30');
  expect(screen.getByText(/entre 8h e 21h/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /confirmar agendamento/i })).toBeDisabled();
});
```

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar** o componente e plugá-lo no modal, substituindo o
  `<p>{avisoDaJanela(janela)}</p>` de hoje. Mantenha `avisoDaJanela` como
  fallback textual quando a API não devolver faixas (loja antiga, erro de rede).

**D9 (trava 08:00–21:00):** o spec deixou "a confirmar". Este plano implementa a
trava — sem ela, agendar às 22h puxa **todo mundo** para as 21h pela regra do
silêncio, e o dono não entenderia por quê. Se o dono decidir o contrário,
remover é apagar `horarioPermitido` do modal; o backend continua correto porque
a regra de silêncio vive na função pura.

- [ ] **Step 4: Rodar e ver passar.**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(campanha): linha do dia no modal de agendamento + trava de horário"
```

---

### Task 10: Painel — a campanha rodando

**Files:**
- Modify: `pastita-dash/src/pages/marketing/whatsapp/WhatsAppCampaignsPage.tsx`
  (link para o detalhe) e a página de detalhe da campanha
- Modify: `pastita-dash/src/services/campaigns.ts` (`getFaixasDaCampanha`)
- Test: `pastita-dash/src/pages/marketing/whatsapp/__tests__/CampanhaEmAndamento.test.tsx`

**Interfaces:**
- Consumes: `GET /campaigns/{id}/faixas/`, `<LinhaDoDia modo="rodando">`.

- [ ] **Step 1: Escrever o teste que falha**

```tsx
it('faixa já enviada mostra o visto e a contagem', () => {
  expect(screen.getByRole('listitem', { name: /11h · 3 enviadas/i })).toBeInTheDocument();
});

it('a próxima faixa aparece em destaque com quanto falta', () => {
  expect(screen.getByText(/próxima às 20h · em 8h30/i)).toBeInTheDocument();
});

it('avisa quem mudou de horário depois do agendamento', () => {
  expect(screen.getByText(/Juliana falou com a loja às 15:10 — agora recebe às 20h/i))
    .toBeInTheDocument();
});

it('mostra o que foi gasto em template: nada', () => {
  expect(screen.getByText(/R\$ 0,00 em template/i)).toBeInTheDocument();
});

it('dá para pausar a campanha', async () => {
  await userEvent.click(screen.getByRole('button', { name: /pausar/i }));
  expect(pausar).toHaveBeenCalledWith(campanha.id);
});
```

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(campanha): tela da campanha rodando com a linha do dia ao vivo"
```

---

### Task 11: Fechamento — suíte inteira, baseline e deploy

- [ ] **Step 1: Suíte de campanhas + conversas no backend**

```bash
docker exec -e TEST_DB_HOST=pastita_test_db -e DJANGO_SETTINGS_MODULE=config.settings.test \
  pastita_web /opt/venv/bin/python -m pytest apps/campaigns apps/conversations apps/whatsapp -q
```
Compare com o baseline conhecido (17 falhas pré-existentes de contrato de
superuser). **Diff zero** é o critério; qualquer falha nova é regressão desta
branch.

- [ ] **Step 2: Suíte do painel**

```bash
cd /home/graco/WORK/pastita-dash && npm test
```

- [ ] **Step 3: Deploy do backend** (padrão da casa)

```bash
for f in <arquivos alterados>; do
  for c in pastita_web pastita_celery pastita_celery_beat; do docker cp $f $c:/app/$f; done
done
docker exec pastita_web /opt/venv/bin/python manage.py migrate campaigns
docker restart pastita_celery pastita_celery_beat pastita_web
docker commit --pause=false pastita_web pastita_backend:latest
```
Nunca `docker compose build` (disco em 91–93%). `docker commit` sem
`--pause=false` derruba o healthcheck por ~30s.

- [ ] **Step 4: Prova em produção**

Agende uma campanha de teste para o próprio número do dono, com a última
mensagem dele há ~23h, e confirme que a rodada antecipa o envio para 1h antes do
fechamento e registra `R$ 0,00 em template`.

- [ ] **Step 5: Atualizar a memória**

Escreva/atualize `project_janela_24h_e_evolution_set16.md`: o que ficou no ar,
o que a rodada faz, e que a decisão D9 foi implementada como trava de tela.

---

## Auto-revisão

**Cobertura do spec:** D1 → Task 3; D2/D3 → Tasks 1 e 5; D4 → Task 1 (+ trava da
Task 9); D5 → Task 1; D6 → Task 5 (alvo recalculado, `alvo_previsto` só exibe);
D7 → Tasks 3 e 6; D8 → Tasks 8–10; D9 → Task 9. Seção 4 do spec: itens 1→Tasks
1–2, 2→Task 3, 3→Tasks 5–6, 4→Task 4, 5→Task 7, 6→Task 7, 7→Task 9, 8→Task 10,
9→Task 9. Seção 6 (erros): corrida→Task 4, `131047`→Task 5, worker fora do
ar→Tasks 4 e 5, sem fuso→Task 2, pausa→Task 5, mudança de horário→Task 5 (conta
ao vivo), template→Tasks 3 e 6. Seção 7 (testes): coberta tarefa a tarefa.

**Nomes consistentes:** `horario_alvo`, `fechamentos_por_chave`,
`fuso_da_campanha`, `processar_rodada_da_janela`, `reservar`,
`liberar_reservas_presas`, `MARCA`, `montarLinhaDoDia`, `horarioPermitido`,
`resumoDaAgenda` — mesmos nomes em todas as tarefas que os consomem.

**Fora do escopo (spec, seção 8):** Evolution API, Instagram/Messenger,
`ScheduledMessage` avulsa e fallback para template pago **não** entram aqui.
