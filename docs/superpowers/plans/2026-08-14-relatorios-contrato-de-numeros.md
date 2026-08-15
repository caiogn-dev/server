# Contrato de Números dos Relatórios — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer todo número exibido declarar sua regra e seu eixo, e fechar o vazamento que deixou R$ 306,00 de vendas entregues fora do faturamento.

**Architecture:** O módulo `apps/stores/metrics/` já é a definição única de receita e está correto — inclusive já tem `totais()`, `contagem_operacional()` e `mes_corrente()`. O trabalho é (a) fazer o caminho de mudança de status do painel delegar ao model, onde mora a regra do dinheiro, (b) fazer os cartões usarem as funções que já existem em vez de somar por conta própria, e (c) travar com um teste que compara todas as superfícies.

**Tech Stack:** Django 4 + DRF (server2), React + Vite + Jest (pastita-dash), pytest no harness Docker.

**Spec:** `docs/superpowers/specs/2026-08-14-relatorios-contrato-de-numeros-design.md`

## Desvio consciente em relação ao spec

O spec propõe um dataclass `Numero(valor, regra, eixo, rotulo)` em
`apps/stores/metrics/contrato.py`. Este plano **não o cria**: os endpoints
passam a emitir `regra` e `eixo` como campos ao lado do número (Task 5), o que
cumpre o contrato — "todo número declara sua regra e seu eixo" — sem uma camada
de serialização a mais. YAGNI: um dataclass que existe para virar dict no
serializer é cerimônia. Se um terceiro consumidor precisar da mesma estrutura,
aí ele nasce, com uso real justificando a forma.

## Global Constraints

- **Testes rodam no harness Docker, nunca contra produção.** Comando padrão:
  `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.test -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v "$PWD":/app -w /app pastita_backend:latest -m pytest <alvo> -q -p no:randomly`
- **NUNCA rodar duas suítes ao mesmo tempo** — dividem o mesmo Postgres e a disputa gera falha que não existe no código.
- Painel: `npx jest <alvo>` e `npx tsc --noEmit -p tsconfig.json`.
- Commits em português. Mensagem por heredoc em arquivo, nunca com crase inline (a substituição do bash come palavras).
- `git add` por arquivo. **Nunca `git add -A`** — há outra sessão trabalhando em `apps/nutrition` e `apps/fiscal`.
- Deploy: `docker cp` nos três containers (`pastita_web`, `pastita_celery`, `pastita_celery_beat`) → `docker restart` → `docker commit pastita_web pastita_backend:latest`.
- Dinheiro é `Decimal`. Nunca `float` em cálculo de valor.

---

### Task 1: Mudar status vira uma implementação só

**Files:**
- Modify: `apps/stores/services/order_service.py:98-160`
- Test: `apps/stores/tests/test_status_unico.py` (criar)

**Interfaces:**
- Consumes: `StoreOrder.update_status(self, new_status: str, notify: bool = True)` — o método do model, que já contém a regra `OFFLINE_PAYMENT_METHODS = {'cash'}`.
- Produces: `OrderService.update_status(order, new_status, notify_customer=True, notes=None) -> Dict[str, Any]` — assinatura inalterada; muda só o miolo.

- [ ] **Step 1: Escrever o teste que falha**

Criar `apps/stores/tests/test_status_unico.py`:

```python
"""Mudar status é UMA implementação, e ela sabe da regra do dinheiro.

Medido em produção em 14/08: 28 pedidos em dinheiro entregues, 26 pagos, 2 não.
R$ 306,00 entregues em mãos e fora do faturamento (CE-2607316642, R$ 95,00, e
KER2608076764, R$ 211,00).

A causa: `OrderService.update_status` — o caminho do PAINEL — reescreve toda a
lógica de timestamps, chama `order.save()` e nunca chama
`StoreOrder.update_status`, que é onde mora "dinheiro entregue vira pago". Ele
trata `cancelled` como caso especial e não trata `delivered`.

Duas implementações da mesma decisão sempre divergem. Esta diverge em dinheiro.
"""
from decimal import Decimal

import pytest

from apps.stores.models import StoreOrder
from apps.stores.services.order_service import OrderService
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


def _pedido(loja, metodo='cash', status='out_for_delivery'):
    return StoreOrder.objects.create(
        store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
        status=status, payment_status='pending', payment_method=metodo,
        customer_phone='+5563984143551', customer_name='gabriela',
    )


@pytest.mark.django_db
class TestDinheiroEntregueViraReceita:
    def test_o_caminho_do_painel_marca_pago(self, loja):
        """O bug dos R$ 306: entregar pelo painel não liquidava a venda."""
        pedido = _pedido(loja)

        OrderService().update_status(pedido, 'delivered', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'paid'

    def test_e_carimba_quando_foi_pago(self, loja):
        pedido = _pedido(loja)

        OrderService().update_status(pedido, 'delivered', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.paid_at is not None

    def test_concluir_tambem_liquida(self, loja):
        pedido = _pedido(loja, status='delivered')

        OrderService().update_status(pedido, 'completed', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'paid'


@pytest.mark.django_db
class TestOQueNaoPodeMudar:
    def test_pix_entregue_NAO_e_marcado_pago(self, loja):
        """Online paga por webhook ANTES de entregar. Marcar aqui inventaria
        receita de um PIX que o cliente nunca pagou."""
        pedido = _pedido(loja, metodo='pix')

        OrderService().update_status(pedido, 'delivered', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'pending'

    def test_transicao_invalida_continua_recusada(self, loja):
        pedido = _pedido(loja, status='pending')

        r = OrderService().update_status(pedido, 'delivered', notify_customer=False)

        assert r['success'] is False
        pedido.refresh_from_db()
        assert pedido.status == 'pending'

    def test_o_timestamp_de_entrega_continua_preenchido(self, loja):
        pedido = _pedido(loja)

        OrderService().update_status(pedido, 'delivered', notify_customer=False)

        pedido.refresh_from_db()
        assert pedido.delivered_at is not None

    def test_a_nota_continua_sendo_anexada(self, loja):
        pedido = _pedido(loja)

        OrderService().update_status(
            pedido, 'delivered', notify_customer=False, notes='deixado na portaria',
        )

        pedido.refresh_from_db()
        assert 'portaria' in pedido.notes

    def test_cancelar_continua_liquidando_o_pagamento(self, loja):
        """Regressão: o dropdown do painel cancela por aqui."""
        pedido = _pedido(loja, status='pending')

        r = OrderService().update_status(pedido, 'cancelled', notify_customer=False)

        assert r['success'] is True
        pedido.refresh_from_db()
        assert pedido.status == 'cancelled'
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.test -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v "$PWD":/app -w /app pastita_backend:latest -m pytest apps/stores/tests/test_status_unico.py -q -p no:randomly`

Expected: FAIL em `test_o_caminho_do_painel_marca_pago` — `assert 'pending' == 'paid'`.

- [ ] **Step 3: Delegar ao model**

Em `apps/stores/services/order_service.py`, substituir o bloco que vai de
`old_status = order.status` até `order.save()` (linhas ~137-159) por:

```python
        old_status = order.status

        if notes:
            order.notes = (
                f"{order.notes}\n\n[{timezone.now().isoformat()}] "
                f"Status: {new_status} - {notes}"
            ).strip()

        # Delega ao model em vez de reescrever. É lá que mora a regra que faz
        # a venda em dinheiro virar receita ao ser entregue — e reescrever os
        # timestamps aqui era o que deixava R$ 306,00 entregues em mãos fora
        # do faturamento (CE-2607316642 e KER2608076764, medidos em 14/08).
        #
        # `notify=False`: a notificação do cliente é decidida abaixo por este
        # serviço, e deixar os dois notificarem manda mensagem repetida.
        order.update_status(new_status, notify=False)
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: mesmo comando do Step 2.
Expected: PASS, 7 testes.

- [ ] **Step 5: Rodar a suíte de pedidos inteira (regressão)**

Run: `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.test -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v "$PWD":/app -w /app pastita_backend:latest -m pytest apps/stores -q -p no:randomly`

Expected: sem falha nova em relação à baseline (1271 passed, 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add apps/stores/services/order_service.py apps/stores/tests/test_status_unico.py
cat > /tmp/t1.txt <<'MSG'
fix: mudar status do pedido vira uma implementacao so

OrderService.update_status — o caminho do painel — reescrevia toda a logica de
timestamps e nunca chamava StoreOrder.update_status, onde mora a regra
"dinheiro entregue vira pago". Tratava cancelled como caso especial e nao
tratava delivered.

Medido em 14/08: 28 pedidos em dinheiro entregues, 26 pagos, 2 nao. R$ 306,00
entregues em maos e fora do faturamento.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
git commit -F /tmp/t1.txt
```

---

### Task 2: O `/entregue` do WhatsApp entra na mesma regra

**Files:**
- Modify: `apps/whatsapp/services/comandos.py` (funções `_executar`, ramos `entregue` e `cancelar`)
- Test: `apps/whatsapp/tests/test_executar_comandos.py` (acrescentar)

**Interfaces:**
- Consumes: `StoreOrder.update_status(new_status, notify=False)` (Task 1 não muda esta assinatura).
- Produces: nada novo.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao fim de `apps/whatsapp/tests/test_executar_comandos.py`:

```python


@pytest.mark.django_db
class TestOAtalhoLiquidaAVenda:
    """`/entregue` também setava o status na mão e pulava a regra do dinheiro.

    Escrito em 14/08 com o mesmo defeito que causou os R$ 306,00 — a terceira
    cópia da mesma decisão.
    """

    def test_entregue_em_dinheiro_marca_pago(self, loja):
        from apps.stores.models import StoreOrder

        pedido = StoreOrder.objects.create(
            store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
            status='out_for_delivery', payment_status='pending',
            payment_method='cash', customer_phone='+5563984143551',
        )

        r = executar('entregue', '', conversa=_conversa(), store=loja, confirmado=True)

        assert r.ok
        pedido.refresh_from_db()
        assert pedido.payment_status == 'paid'

    def test_entregue_em_pix_NAO_marca_pago(self, loja):
        from apps.stores.models import StoreOrder

        pedido = StoreOrder.objects.create(
            store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
            status='out_for_delivery', payment_status='pending',
            payment_method='pix', customer_phone='+5563984143551',
        )

        executar('entregue', '', conversa=_conversa(), store=loja, confirmado=True)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'pending'
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.test -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v "$PWD":/app -w /app pastita_backend:latest -m pytest apps/whatsapp/tests/test_executar_comandos.py -q -p no:randomly`

Expected: FAIL em `test_entregue_em_dinheiro_marca_pago`.

- [ ] **Step 3: Delegar ao model**

Em `apps/whatsapp/services/comandos.py`, no ramo `entregue`, trocar:

```python
    if nome == 'entregue':
        from apps.stores.models import StoreOrder

        pedido.status = StoreOrder.OrderStatus.DELIVERED
        pedido.save(update_fields=['status', 'updated_at'])
        return Resultado(True, f'Pedido {pedido.order_number} marcado como entregue.')
```

por:

```python
    if nome == 'entregue':
        from apps.stores.models import StoreOrder

        # `update_status` do model, e não `save()` na mão: é lá que a venda em
        # dinheiro vira receita ao ser entregue. Setar o campo direto foi o que
        # deixou R$ 306,00 fora do faturamento pelo caminho do painel.
        pedido.update_status(StoreOrder.OrderStatus.DELIVERED, notify=False)
        return Resultado(True, f'Pedido {pedido.order_number} marcado como entregue.')
```

E no ramo `cancelar`, trocar o `pedido.status = ...; pedido.save(...)` por:

```python
        pedido.update_status(StoreOrder.OrderStatus.CANCELLED, notify=False)
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: mesmo comando do Step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/whatsapp/services/comandos.py apps/whatsapp/tests/test_executar_comandos.py
cat > /tmp/t2.txt <<'MSG'
fix: /entregue e /cancelar delegam ao model

Terceira copia da mesma decisao: setavam o status na mao e pulavam a regra que
faz a venda em dinheiro virar receita.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
git commit -F /tmp/t2.txt
```

---

### Task 3: Comando que recupera os R$ 306

**Files:**
- Create: `apps/stores/management/commands/liquidar_entregas_em_dinheiro.py`
- Test: `apps/stores/tests/test_liquidar_entregas_em_dinheiro.py`

**Interfaces:**
- Consumes: `StoreOrder.OFFLINE_PAYMENT_METHODS` não é público; usar a constante local `METODOS_OFFLINE = {'cash'}` no comando, com comentário apontando para `apps/stores/models/order.py`.
- Produces: comando `liquidar_entregas_em_dinheiro --dry-run --loja <slug>`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `apps/stores/tests/test_liquidar_entregas_em_dinheiro.py`:

```python
"""Recupera as vendas entregues em dinheiro que nunca liquidaram.

O conserto do Task 1 vale de agora em diante. Este comando resolve o passivo:
R$ 306,00 medidos em 14/08 (CE-2607316642, R$ 95,00, e KER2608076764,
R$ 211,00) — entregues, dinheiro recebido em mãos, `payment_status=pending`.

⚠️ `paid_at` recebe `delivered_at`, NUNCA `now()`. Uma venda de 31/07 marcada
como paga hoje apareceria no faturamento de hoje: o furo do relatório sairia do
lugar em vez de fechar.
"""
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


def _entregue_sem_liquidar(loja, metodo='cash', dias_atras=14):
    quando = timezone.now() - timezone.timedelta(days=dias_atras)
    p = StoreOrder.objects.create(
        store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
        status='delivered', payment_status='pending', payment_method=metodo,
        customer_phone='+5563984143551',
    )
    StoreOrder.objects.filter(id=p.id).update(delivered_at=quando)
    p.refresh_from_db()
    return p


@pytest.mark.django_db
class TestRecuperacao:
    def test_marca_pago(self, loja):
        p = _entregue_sem_liquidar(loja)

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.payment_status == 'paid'

    def test_paid_at_e_a_data_da_ENTREGA(self, loja):
        """Marcar com `now()` moveria a venda de 31/07 para o faturamento de hoje."""
        p = _entregue_sem_liquidar(loja, dias_atras=14)
        entrega = p.delivered_at

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.paid_at == entrega

    def test_dry_run_nao_grava(self, loja):
        p = _entregue_sem_liquidar(loja)

        call_command('liquidar_entregas_em_dinheiro', dry_run=True)

        p.refresh_from_db()
        assert p.payment_status == 'pending'

    def test_rodar_duas_vezes_nao_muda_nada(self, loja):
        p = _entregue_sem_liquidar(loja)

        call_command('liquidar_entregas_em_dinheiro')
        p.refresh_from_db()
        primeiro = p.paid_at
        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.paid_at == primeiro

    def test_filtra_por_loja(self, loja):
        outra = make_store(name='Kero Kero')
        de_outra = _entregue_sem_liquidar(outra)

        call_command('liquidar_entregas_em_dinheiro', loja=loja.slug)

        de_outra.refresh_from_db()
        assert de_outra.payment_status == 'pending'


@pytest.mark.django_db
class TestOQueNaoPodeSerTocado:
    def test_pix_entregue_e_pendente_NAO_vira_pago(self, loja):
        """Não pagou. Marcar aqui inventaria receita."""
        p = _entregue_sem_liquidar(loja, metodo='pix')

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.payment_status == 'pending'

    def test_cancelado_em_dinheiro_nao_vira_pago(self, loja):
        p = _entregue_sem_liquidar(loja)
        StoreOrder.objects.filter(id=p.id).update(status='cancelled')

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.payment_status == 'pending'

    def test_sem_delivered_at_nao_inventa_data(self, loja):
        """Sem data de entrega não há data de pagamento defensável."""
        p = StoreOrder.objects.create(
            store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
            status='delivered', payment_status='pending', payment_method='cash',
            customer_phone='+5563984143551',
        )

        call_command('liquidar_entregas_em_dinheiro')

        p.refresh_from_db()
        assert p.payment_status == 'pending'
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.test -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v "$PWD":/app -w /app pastita_backend:latest -m pytest apps/stores/tests/test_liquidar_entregas_em_dinheiro.py -q -p no:randomly`

Expected: FAIL com `CommandError: Unknown command`.

- [ ] **Step 3: Escrever o comando**

Criar `apps/stores/management/commands/liquidar_entregas_em_dinheiro.py`:

```python
"""Liquida vendas entregues em dinheiro que nunca viraram receita.

O conserto em `OrderService.update_status` vale de agora em diante; este
comando resolve o passivo. Medido em 14/08: R$ 306,00 em dois pedidos
(CE-2607316642 e KER2608076764) entregues, dinheiro recebido em mãos e
`payment_status=pending`.

⚠️ `paid_at` recebe `delivered_at`, nunca `now()`: marcar hoje uma venda de
31/07 tiraria o furo do lugar em vez de fechá-lo.

    python manage.py liquidar_entregas_em_dinheiro --dry-run
    python manage.py liquidar_entregas_em_dinheiro --loja ce-saladas
"""
from django.core.management.base import BaseCommand
from django.db import transaction

#: Espelha `OFFLINE_PAYMENT_METHODS` em `apps/stores/models/order.py`. Pago em
#: mãos na entrega — o único caso em que entregar é a prova do pagamento.
METODOS_OFFLINE = {'cash'}


class Command(BaseCommand):
    help = 'Marca como pagas as entregas em dinheiro que nunca liquidaram.'

    def add_arguments(self, parser):
        parser.add_argument('--loja', help='slug da loja; padrão é todas')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='lista o que seria liquidado, sem gravar',
        )

    def handle(self, *args, **opts):
        from apps.stores.models import StoreOrder

        pendentes = (
            StoreOrder.objects
            .filter(
                status__in=[
                    StoreOrder.OrderStatus.DELIVERED,
                    StoreOrder.OrderStatus.COMPLETED,
                ],
                payment_method__in=METODOS_OFFLINE,
                delivered_at__isnull=False,
            )
            .exclude(payment_status=StoreOrder.PaymentStatus.PAID)
            .select_related('store')
            .order_by('delivered_at')
        )
        if opts.get('loja'):
            pendentes = pendentes.filter(store__slug=opts['loja'])

        total = 0
        with transaction.atomic():
            for pedido in pendentes:
                self.stdout.write(
                    f'  {pedido.store.slug:12} {pedido.order_number:16} '
                    f'entregue {pedido.delivered_at:%d/%m %H:%M}  R$ {pedido.total}'
                )
                total += pedido.total
                StoreOrder.objects.filter(id=pedido.id).update(
                    payment_status=StoreOrder.PaymentStatus.PAID,
                    paid_at=pedido.delivered_at,
                )

            if opts.get('dry_run'):
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(
                    f'[dry-run] {pendentes.count()} pedidos, R$ {total} — nada gravado'
                ))
                return

        self.stdout.write(self.style.SUCCESS(
            f'{pendentes.count()} pedidos liquidados, R$ {total} de volta ao faturamento.'
        ))
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: mesmo comando do Step 2.
Expected: PASS, 8 testes.

- [ ] **Step 5: Rodar em produção, primeiro em seco**

```bash
for c in pastita_web pastita_celery pastita_celery_beat; do
  docker cp apps/stores/management/commands/liquidar_entregas_em_dinheiro.py $c:/app/apps/stores/management/commands/
done
docker exec pastita_web python manage.py liquidar_entregas_em_dinheiro --dry-run
```

Expected: lista `CE-2607316642` (R$ 95,00) e `KER2608076764` (R$ 211,00), total R$ 306,00.

Só depois de conferir a lista, rodar sem `--dry-run`.

- [ ] **Step 6: Commit**

```bash
git add apps/stores/management/commands/liquidar_entregas_em_dinheiro.py apps/stores/tests/test_liquidar_entregas_em_dinheiro.py
cat > /tmp/t3.txt <<'MSG'
feat: comando que recupera entregas em dinheiro nao liquidadas

paid_at recebe delivered_at e nunca now(): marcar hoje uma venda de 31/07
tiraria o furo do lugar em vez de fecha-lo.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
git commit -F /tmp/t3.txt
```

---

### Task 4: O teste de coerência entre superfícies

**Files:**
- Create: `apps/stores/tests/test_coerencia_dos_relatorios.py`

**Interfaces:**
- Consumes: `metrics.totais(loja, janela) -> {'receita','pedidos','ticket_medio','frete','desconto'}`; `metrics.de_datas(inicio, fim) -> Janela`.
- Produces: nada — é trava.

- [ ] **Step 1: Escrever o teste (vai falhar, e o vermelho é o mapa)**

Criar `apps/stores/tests/test_coerencia_dos_relatorios.py`:

```python
"""Todas as telas dizem o MESMO número para o mesmo período.

A divergência entre telas não nasce de conta errada — nasce de cada tela poder
escolher a sua regra em silêncio. `apps/stores/metrics/__init__.py` já diz, no
próprio docstring, que "nenhuma view deve conter `Sum('total')`". A regra
existia e não era cobrada.

Este teste é o cobrador. Sem ele, a próxima tela inventa a regra dela e o
conserto envelhece em duas semanas.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores import metrics
from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def vendas(loja):
    """Um cenário com tudo que costuma confundir relatório."""
    agora = timezone.now()
    feito = []
    for valor, status, pago in [
        ('100.00', 'delivered', 'paid'),      # conta
        ('50.00', 'delivered', 'paid'),       # conta
        ('30.00', 'cancelled', 'paid'),       # NÃO conta: cancelado
        ('20.00', 'delivered', 'pending'),    # NÃO conta: não pago
    ]:
        p = StoreOrder.objects.create(
            store=loja, total=Decimal(valor), subtotal=Decimal(valor),
            status=status, payment_status=pago, payment_method='pix',
            customer_phone='+5563984143551',
        )
        StoreOrder.objects.filter(id=p.id).update(paid_at=agora)
        feito.append(p)
    return feito


@pytest.fixture
def cliente_api(loja):
    U = get_user_model()
    c = APIClient()
    c.force_authenticate(loja.owner)
    return c


@pytest.mark.django_db
class TestTodasAsTelasConcordam:
    def _janela(self):
        hoje = timezone.localdate()
        return hoje, hoje

    def test_referencia_conta_so_o_que_deve(self, loja, vendas):
        inicio, fim = self._janela()

        t = metrics.totais(loja, metrics.de_datas(inicio, fim))

        assert t['receita'] == Decimal('150.00')
        assert t['pedidos'] == 2

    def test_reports_revenue_bate_com_a_referencia(self, loja, vendas, cliente_api):
        inicio, fim = self._janela()
        t = metrics.totais(loja, metrics.de_datas(inicio, fim))

        r = cliente_api.get(
            '/api/v1/stores/reports/revenue/',
            {'store': loja.slug, 'start_date': str(inicio), 'end_date': str(fim)},
        )

        assert r.status_code == 200
        assert Decimal(str(r.data['summary']['total_revenue'])) == t['receita']
        assert r.data['summary']['total_orders'] == t['pedidos']

    def test_dashboard_bate_com_a_referencia(self, loja, vendas, cliente_api):
        """O bug: 'orders' contava TODOS e 'revenue' só os pagos."""
        janela = metrics.mes_corrente()
        t = metrics.totais(loja, janela)

        r = cliente_api.get('/api/v1/stores/reports/dashboard/', {'store': loja.slug})

        assert r.status_code == 200
        assert Decimal(str(r.data['month']['revenue'])) == t['receita']
        assert r.data['month']['orders'] == t['pedidos'], (
            'o cartão conta pedidos por uma regra e receita por outra'
        )

    def test_o_ticket_do_cartao_e_divisivel(self, loja, vendas, cliente_api):
        """É a leitura que o cartão convida a fazer — tem que fechar."""
        r = cliente_api.get('/api/v1/stores/reports/dashboard/', {'store': loja.slug})
        mes = r.data['month']

        esperado = Decimal(str(mes['revenue'])) / mes['orders']

        assert abs(esperado - Decimal('75.00')) < Decimal('0.01')


@pytest.mark.django_db
class TestOsRotulosDizemAVerdade:
    def test_month_e_o_mes_do_calendario(self, loja, vendas, cliente_api):
        """'month' usava `hoje - 30 dias`. Para o dono, mês tem primeiro dia."""
        r = cliente_api.get('/api/v1/stores/reports/dashboard/', {'store': loja.slug})

        janela = metrics.mes_corrente()
        assert Decimal(str(r.data['month']['revenue'])) == metrics.totais(
            loja, janela,
        )['receita']
```

Acrescentar, ao mesmo arquivo, as superfícies restantes:

```python


@pytest.mark.django_db
class TestAsOutrasSuperficies:
    """O spec lista seis superfícies. Estas três têm recorte próprio, e o teste
    respeita o recorte em vez de exigir igualdade cega — exigir que o caixa
    bata com o faturamento total seria errado: o caixa é só a gaveta.
    """

    def test_a_exportacao_de_pedidos_traz_os_mesmos_pedidos(self, loja, vendas, cliente_api):
        inicio = fim = timezone.localdate()
        t = metrics.totais(loja, metrics.de_datas(inicio, fim))

        r = cliente_api.get(
            '/api/v1/stores/reports/orders/export/',
            {'store': loja.slug, 'start_date': str(inicio), 'end_date': str(fim),
             'somente_receita': '1'},
        )

        assert r.status_code == 200
        linhas = [l for l in r.content.decode().splitlines() if l.strip()]
        # cabeçalho + uma linha por pedido de receita
        assert len(linhas) - 1 == t['pedidos'], (
            'a exportação traz um conjunto diferente do faturamento'
        )

    def test_o_caixa_conta_so_a_gaveta(self, loja):
        """Recorte próprio e correto: só dinheiro, só na janela da sessão.

        Não deve bater com o faturamento total — deve bater com a parte dele
        que é dinheiro. Confundir os dois faz o fechamento acusar quebra que
        não existe.
        """
        from apps.stores.models import StoreCashSession

        agora = timezone.now()
        sessao = StoreCashSession.objects.create(
            store=loja, opened_at=agora - timezone.timedelta(hours=1),
            opening_amount=Decimal('0.00'), status='open',
        )
        p = StoreOrder.objects.create(
            store=loja, total=Decimal('40.00'), subtotal=Decimal('40.00'),
            status='delivered', payment_status='paid', payment_method='cash',
            customer_phone='+5563984143551',
        )
        StoreOrder.objects.filter(id=p.id).update(paid_at=agora)

        assert sessao.expected_amount == Decimal('40.00')

    def test_o_caixa_ignora_pix(self, loja):
        """PIX não entra na gaveta — é o recorte que justifica o filtro."""
        from apps.stores.models import StoreCashSession

        agora = timezone.now()
        sessao = StoreCashSession.objects.create(
            store=loja, opened_at=agora - timezone.timedelta(hours=1),
            opening_amount=Decimal('0.00'), status='open',
        )
        p = StoreOrder.objects.create(
            store=loja, total=Decimal('40.00'), subtotal=Decimal('40.00'),
            status='delivered', payment_status='paid', payment_method='pix',
            customer_phone='+5563984143551',
        )
        StoreOrder.objects.filter(id=p.id).update(paid_at=agora)

        assert sessao.expected_amount == Decimal('0.00')
```

⚠️ Se `reports/orders/export/` não aceitar `somente_receita`, o teste vai
denunciar que a exportação usa outra regra — isso É o achado, não um erro do
teste. Nesse caso, acrescentar o parâmetro ao endpoint faz parte do Task 5.

`ai_insights` fica de fora de propósito: é resumo em texto gerado por LLM e
cacheado, não uma superfície numérica. Travar o texto do modelo num teste de
coerência mediria o modelo, não a regra.

- [ ] **Step 2: Rodar e ver o mapa do que falta**

Run: `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.test -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v "$PWD":/app -w /app pastita_backend:latest -m pytest apps/stores/tests/test_coerencia_dos_relatorios.py -q -p no:randomly`

Expected: `test_referencia_conta_so_o_que_deve` e `test_reports_revenue_bate_com_a_referencia` PASSAM; `test_dashboard_bate_com_a_referencia`, `test_o_ticket_do_cartao_e_divisivel` e `test_month_e_o_mes_do_calendario` FALHAM. Se `de_datas` não aceitar dois `date`, ajustar a chamada conforme a assinatura real em `apps/stores/metrics/janelas.py` antes de seguir.

- [ ] **Step 3: Commit do teste vermelho**

Commitar o teste sozinho documenta o estado. Use `--no-verify` se houver hook que exige suíte verde.

```bash
git add apps/stores/tests/test_coerencia_dos_relatorios.py
cat > /tmp/t4.txt <<'MSG'
test: coerencia entre as telas de relatorio (vermelho, de proposito)

O docstring de apps/stores/metrics ja dizia "nenhuma view deve conter
Sum('total')". A regra existia e nao era cobrada. Este teste e o cobrador.

Falha hoje no cartao do dashboard, que conta pedidos por uma regra e receita
por outra. O verde vem no proximo commit.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
git commit -F /tmp/t4.txt
```

---

### Task 5: O cartão do dashboard passa a usar as métricas

**Files:**
- Modify: `apps/stores/api/export_views.py:550-615`
- Test: `apps/stores/tests/test_coerencia_dos_relatorios.py` (já escrito no Task 4)

**Interfaces:**
- Consumes: `metrics.totais(loja, janela)`, `metrics.contagem_operacional(loja, janela) -> {'pedidos': int, 'por_status': dict}`, `metrics.hoje()`, `metrics.ontem()`, `metrics.ultimos_dias(n)`, `metrics.mes_corrente()`.
- Produces: `GET /stores/reports/dashboard/` com `today`/`week`/`month` contendo `orders` e `revenue` na MESMA regra, mais `operacao` com o volume total e a quebra por status.

- [ ] **Step 1: Substituir a contagem crua**

Em `apps/stores/api/export_views.py`, trocar o bloco:

```python
        # Contagem operacional continua sobre o queryset cru: a operação
        # precisa ver o pedido cancelado, o faturamento não.
        _op = StoreOrder.objects.filter(store=store)
        today_orders = _op.filter(created_at__date=today)
        week_orders = _op.filter(created_at__date__gte=last_7_days)
        month_orders = _op.filter(created_at__date__gte=last_30_days)
```

por:

```python
        # ⚠️ Os dois números de cada cartão vêm da MESMA regra e do MESMO eixo.
        #
        # Antes, `orders` contava TODOS os pedidos por data de criação e
        # `revenue` só os pagos por data de pagamento. Nenhum campo mentia
        # sozinho; a mentira era a divisão que o cartão convidava a fazer —
        # ticket de R$ 57,30 onde o real era R$ 70,19 (medido em 14/08).
        #
        # O volume operacional não sumiu: virou um bloco próprio, que é onde a
        # cozinha quer vê-lo.
        janela_hoje = metrics.hoje()
        janela_semana = metrics.ultimos_dias(8)
        janela_mes = metrics.mes_corrente()

        totais_hoje = metrics.totais(store, janela_hoje)
        totais_semana = metrics.totais(store, janela_semana)
        totais_mes = metrics.totais(store, janela_mes)
        operacao_mes = metrics.contagem_operacional(store, janela_mes)
```

E o `return Response({...})` por:

```python
        return Response({
            'today': {
                'orders': totais_hoje['pedidos'],
                'revenue': float(totais_hoje['receita']),
                'revenue_change': float(totais_hoje['receita'] - yesterday_revenue),
                'revenue_change_percent': round(
                    ((totais_hoje['receita'] - yesterday_revenue) / yesterday_revenue * 100)
                    if yesterday_revenue > 0 else 0, 2
                ),
                'regra': 'receita',
                'eixo': 'pagamento',
            },
            'week': {
                'orders': totais_semana['pedidos'],
                'revenue': float(totais_semana['receita']),
                'avg_daily_revenue': float(totais_semana['receita'] / 7),
                'regra': 'receita',
                'eixo': 'pagamento',
                'rotulo': 'últimos 7 dias',
            },
            'month': {
                'orders': totais_mes['pedidos'],
                'revenue': float(totais_mes['receita']),
                'avg_daily_revenue': float(totais_mes['receita'] / max(today.day, 1)),
                'regra': 'receita',
                'eixo': 'pagamento',
                'rotulo': 'este mês',
            },
            # Volume que passou pela operação — inclui cancelado e não pago.
            # NÃO é faturamento, e o rótulo diz isso.
            'operacao': {
                'pedidos': operacao_mes['pedidos'],
                'por_status': operacao_mes['por_status'],
                'nao_faturados': operacao_mes['pedidos'] - totais_mes['pedidos'],
                'regra': 'operacao',
                'eixo': 'pagamento',
            },
            'alerts': {
                'pending_orders': pending_orders,
                'low_stock_products': low_stock
            }
        })
```

Manter `yesterday_revenue = metrics.totais(store, metrics.ontem())['receita']` como já está, e remover as variáveis `today_revenue`, `week_revenue`, `month_revenue`, `last_7_days` e `last_30_days` que ficaram sem uso.

- [ ] **Step 2: Rodar o teste de coerência**

Run: `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.test -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v "$PWD":/app -w /app pastita_backend:latest -m pytest apps/stores/tests/test_coerencia_dos_relatorios.py -q -p no:randomly`

Expected: PASS, todos.

- [ ] **Step 3: Rodar `apps/stores` inteira**

Expected: sem falha nova vs. baseline.

- [ ] **Step 4: Conferir contra produção**

```bash
for c in pastita_web pastita_celery pastita_celery_beat; do
  docker cp apps/stores/api/export_views.py $c:/app/apps/stores/api/
done
docker restart pastita_web && sleep 22
```

Depois, comparar `month.revenue / month.orders` com `metrics.totais(loja, metrics.mes_corrente())`. Devem ser idênticos.

- [ ] **Step 5: Commit**

```bash
git add apps/stores/api/export_views.py
cat > /tmp/t5.txt <<'MSG'
fix: os dois numeros do cartao passam a ser divisiveis entre si

'orders' contava TODOS os pedidos por data de criacao e 'revenue' so os pagos
por data de pagamento. Nenhum campo mentia sozinho; a mentira era a divisao que
o cartao convidava a fazer — ticket de R$ 57,30 onde o real era R$ 70,19.

O volume operacional virou bloco proprio, que e onde a cozinha quer ve-lo.
E 'month' passa a ser o mes do calendario, nao 30 dias corridos.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
git commit -F /tmp/t5.txt
```

---

### Task 6: O painel mostra o cartão novo

**Files:**
- Modify: `pastita-dash/src/services/reports.ts:120-140` (interface `DashboardStats`)
- Modify: `pastita-dash/src/pages/reports/sections/OverviewSummarySection.tsx`
- Test: `pastita-dash/src/pages/reports/sections/__tests__/OverviewSummarySection.cartao.test.tsx`

**Interfaces:**
- Consumes: `GET /stores/reports/dashboard/` com o formato produzido no Task 5, incluindo `operacao.nao_faturados` e `month.rotulo`. O hook é `useDashboardStats(enabled: boolean)` em `src/hooks/queries/useReports.ts:65`, que chama `reportsService.getDashboardStats()`.
- Produces: nada para tarefas seguintes.

- [ ] **Step 1: Acrescentar os campos novos ao tipo**

Em `src/services/reports.ts`, na interface `DashboardStats`, acrescentar a
`today`/`week`/`month`:

```ts
  /** 'receita' (pago, sem cancelado) ou 'operacao' (tudo). */
  regra: 'receita' | 'operacao';
  /** 'pagamento' (paid_at) ou 'criacao' (created_at). */
  eixo: 'pagamento' | 'criacao';
  /** Como o período se chama para o dono: "este mês", "últimos 7 dias". */
  rotulo?: string;
```

e, no nível de cima:

```ts
  operacao: {
    pedidos: number;
    por_status: Record<string, number>;
    nao_faturados: number;
    regra: 'operacao';
    eixo: 'pagamento';
  };
```

- [ ] **Step 2: Escrever o teste que falha**

Criar `pastita-dash/src/pages/reports/__tests__/cartaoDeFaturamento.test.tsx`:

```tsx
/**
 * O cartão mostra dois números que fecham entre si.
 *
 * Antes: "49 pedidos · R$ 2.807,64" — os 49 eram TODOS os pedidos e os
 * R$ 2.807,64 só os pagos. Dividindo, o dono lia ticket de R$ 57,30 onde o
 * real era R$ 70,19.
 */
import { render, screen } from '@testing-library/react';

import { CartaoDeFaturamento } from '../OverviewSummarySection';

const MES = {
  orders: 40,
  revenue: 2807.64,
  rotulo: 'este mês',
  regra: 'receita',
  eixo: 'pagamento',
};

describe('cartão de faturamento', () => {
  it('mostra o faturamento e a contagem na mesma regra', () => {
    render(<CartaoDeFaturamento periodo={MES} />);

    expect(screen.getByText(/2\.807,64/)).toBeInTheDocument();
    expect(screen.getByText(/40/)).toBeInTheDocument();
  });

  it('mostra o ticket já calculado, para ninguém dividir errado', () => {
    render(<CartaoDeFaturamento periodo={MES} />);

    expect(screen.getByText(/70,19/)).toBeInTheDocument();
  });

  it('diz de que período está falando', () => {
    render(<CartaoDeFaturamento periodo={MES} />);

    expect(screen.getByText(/este mês/i)).toBeInTheDocument();
  });

  it('não some com os não faturados — mostra separado', () => {
    render(
      <CartaoDeFaturamento
        periodo={MES}
        operacao={{ pedidos: 49, nao_faturados: 9, por_status: { cancelled: 7 } }}
      />,
    );

    expect(screen.getByText(/9 não faturados/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Rodar e confirmar que falha**

Run: `cd /home/graco/WORK/pastita-dash && npx jest src/pages/reports/sections/__tests__/OverviewSummarySection.cartao.test.tsx`

Expected: FAIL — componente não existe ou não mostra o ticket.

- [ ] **Step 4: Implementar**

Renderizar `revenue`, `orders`, o ticket calculado (`revenue / orders`, com guarda para `orders === 0`) e o `rotulo`. Abaixo, em tom secundário, `{operacao.nao_faturados} não faturados`.

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `npx jest src/pages/reports` e `npx tsc --noEmit -p tsconfig.json`
Expected: PASS e zero erro de tipo.

- [ ] **Step 6: Commit e push**

```bash
cd /home/graco/WORK/pastita-dash
git add src/services/reports.ts src/pages/reports/sections/OverviewSummarySection.tsx src/pages/reports/sections/__tests__/OverviewSummarySection.cartao.test.tsx
cat > /tmp/t6.txt <<'MSG'
fix: cartao de faturamento mostra ticket calculado e periodo nomeado

Os dois numeros agora vem da mesma regra, o ticket vem pronto para ninguem
dividir errado, e os nao faturados aparecem separados em vez de sumirem.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
git commit -F /tmp/t6.txt && git push origin main
```

---

### Task 7: Fechar o conjunto dos métodos de pagamento

**Files:**
- Modify: `apps/stores/models/order.py:138`
- Create: `apps/stores/migrations/XXXX_normalizar_payment_method.py`
- Test: `apps/stores/tests/test_metodos_de_pagamento.py`

**Interfaces:**
- Produces: `StoreOrder.PaymentMethod` — `TextChoices` com `PIX='pix'`, `CARD='card'`, `CASH='cash'`, `LINK='other'`, `UNKNOWN='unknown'`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `apps/stores/tests/test_metodos_de_pagamento.py`:

```python
"""`payment_method` é um conjunto FECHADO.

Medido em 14/08: pix 74 · cash 37 · '' 5 · other 3 · credit_card 3 · card 3.
`card` e `credit_card` são a mesma coisa escrita de dois jeitos, e nenhum
relatório consegue cortar por método com isso. É pré-requisito do próximo
plano ("pagar na entrega").
"""
import pytest

from apps.stores.models import StoreOrder


class TestOConjunto:
    def test_os_metodos_sao_declarados(self):
        valores = {c[0] for c in StoreOrder.PaymentMethod.choices}

        assert valores == {'pix', 'card', 'cash', 'other', 'unknown'}

    def test_credit_card_nao_existe_mais(self):
        """Dois nomes para cartão é o que impedia cortar o relatório."""
        valores = {c[0] for c in StoreOrder.PaymentMethod.choices}

        assert 'credit_card' not in valores

    def test_cada_metodo_tem_rotulo_legivel(self):
        for _, rotulo in StoreOrder.PaymentMethod.choices:
            assert rotulo and rotulo[0].isupper()
```

- [ ] **Step 2: Rodar e confirmar que falha**

Expected: `AttributeError: type object 'StoreOrder' has no attribute 'PaymentMethod'`.

- [ ] **Step 3: Declarar o conjunto**

Em `apps/stores/models/order.py`, acima do campo:

```python
    class PaymentMethod(models.TextChoices):
        """Conjunto FECHADO. Aberto, virou `card` e `credit_card` convivendo.

        `other` é o link de pagamento avulso (Checkout Pro), onde quem escolhe
        o instrumento é o cliente na página do Mercado Pago — a loja não sabe
        se foi cartão ou PIX, e fingir que sabe seria inventar dado.

        `unknown` é o legado sem método. Adivinhar "provavelmente foi dinheiro"
        colocaria R$ 40,49 na gaveta de um caixa que nunca os viu.
        """
        PIX = 'pix', 'PIX'
        CARD = 'card', 'Cartão'
        CASH = 'cash', 'Dinheiro'
        LINK = 'other', 'Link de pagamento'
        UNKNOWN = 'unknown', 'Não informado'
```

E o campo passa a `models.CharField(max_length=50, blank=True, choices=PaymentMethod.choices)`.

- [ ] **Step 4: Criar a migração de dados**

Run: `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.test -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v "$PWD":/app -w /app pastita_backend:latest manage.py makemigrations stores --name normalizar_payment_method`

Depois, editar a migração gerada e acrescentar:

```python
def normalizar(apps, schema_editor):
    """`credit_card` e `card` eram a mesma coisa; vazio vira `unknown`."""
    StoreOrder = apps.get_model('stores', 'StoreOrder')
    StoreOrder.objects.filter(payment_method='credit_card').update(payment_method='card')
    StoreOrder.objects.filter(payment_method='').update(payment_method='unknown')


def desnormalizar(apps, schema_editor):
    """Não dá para reverter: `card` perdeu a informação de qual era qual."""
    pass
```

e registrar `migrations.RunPython(normalizar, desnormalizar)` em `operations`.

- [ ] **Step 5: Rodar os testes**

Run: `... -m pytest apps/stores/tests/test_metodos_de_pagamento.py apps/stores -q -p no:randomly`
Expected: PASS, sem falha nova vs. baseline.

- [ ] **Step 6: Aplicar em produção**

```bash
for c in pastita_web pastita_celery pastita_celery_beat; do
  docker cp apps/stores/models/order.py $c:/app/apps/stores/models/
  docker cp apps/stores/migrations/ $c:/app/apps/stores/
done
docker exec pastita_web python manage.py migrate stores
```

Conferir depois: nenhum `payment_method` fora do conjunto.

- [ ] **Step 7: Commit**

```bash
git add apps/stores/models/order.py apps/stores/migrations/ apps/stores/tests/test_metodos_de_pagamento.py
cat > /tmp/t7.txt <<'MSG'
fix: payment_method vira conjunto fechado

card e credit_card eram a mesma coisa escrita de dois jeitos, e havia registros
vazios. Nenhum relatorio conseguia cortar por metodo. Pre-requisito do plano de
"pagar na entrega".

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
git commit -F /tmp/t7.txt
```

---

### Task 8: Faturamento por método e por canal

**Files:**
- Modify: `apps/stores/metrics/series.py` (nova função)
- Modify: `apps/stores/api/export_views.py` (endpoint de revenue)
- Test: `apps/stores/tests/test_quebra_por_metodo_e_canal.py`

**Interfaces:**
- Produces: `metrics.quebra_por(loja, janela, campo: str) -> list[dict]` com `[{'chave': str, 'receita': Decimal, 'pedidos': int}]`, ordenado por receita decrescente.

- [ ] **Step 1: Escrever o teste que falha**

Criar `apps/stores/tests/test_quebra_por_metodo_e_canal.py`:

```python
"""Faturamento cortado por método de pagamento e por canal.

O dono pediu: "relatório raso demais / falta corte". Sem isto não dá para
responder "quanto entrou em dinheiro?" nem "o WhatsApp vende mais que o site?".
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.stores import metrics
from apps.stores.models import StoreOrder
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def vendas(loja):
    agora = timezone.now()
    for valor, metodo, canal in [
        ('100.00', 'pix', 'whatsapp'),
        ('50.00', 'pix', 'site'),
        ('30.00', 'cash', 'whatsapp'),
    ]:
        p = StoreOrder.objects.create(
            store=loja, total=Decimal(valor), subtotal=Decimal(valor),
            status='delivered', payment_status='paid', payment_method=metodo,
            customer_phone='+5563984143551', metadata={'source': canal},
        )
        StoreOrder.objects.filter(id=p.id).update(paid_at=agora)


@pytest.mark.django_db
class TestQuebraPorMetodo:
    def test_soma_por_metodo(self, loja, vendas):
        janela = metrics.de_datas(timezone.localdate(), timezone.localdate())

        linhas = metrics.quebra_por(loja, janela, 'payment_method')

        por = {l['chave']: l['receita'] for l in linhas}
        assert por['pix'] == Decimal('150.00')
        assert por['cash'] == Decimal('30.00')

    def test_ordena_do_maior_pro_menor(self, loja, vendas):
        janela = metrics.de_datas(timezone.localdate(), timezone.localdate())

        linhas = metrics.quebra_por(loja, janela, 'payment_method')

        assert linhas[0]['chave'] == 'pix'

    def test_conta_pedidos_junto(self, loja, vendas):
        janela = metrics.de_datas(timezone.localdate(), timezone.localdate())

        linhas = metrics.quebra_por(loja, janela, 'payment_method')

        assert next(l for l in linhas if l['chave'] == 'pix')['pedidos'] == 2


@pytest.mark.django_db
class TestQuebraPorCanal:
    def test_soma_por_canal(self, loja, vendas):
        janela = metrics.de_datas(timezone.localdate(), timezone.localdate())

        linhas = metrics.quebra_por(loja, janela, 'metadata__source')

        por = {l['chave']: l['receita'] for l in linhas}
        assert por['whatsapp'] == Decimal('130.00')
        assert por['site'] == Decimal('50.00')


@pytest.mark.django_db
class TestObedeceARegraDeReceita:
    def test_cancelado_nao_entra_na_quebra(self, loja, vendas):
        """A quebra usa a MESMA regra do total. Somadas, as linhas têm que
        fechar com `totais()` — senão a tela mostra um bolo maior que o todo."""
        p = StoreOrder.objects.create(
            store=loja, total=Decimal('999.00'), subtotal=Decimal('999.00'),
            status='cancelled', payment_status='paid', payment_method='pix',
            customer_phone='+5563984143551',
        )
        StoreOrder.objects.filter(id=p.id).update(paid_at=timezone.now())
        janela = metrics.de_datas(timezone.localdate(), timezone.localdate())

        linhas = metrics.quebra_por(loja, janela, 'payment_method')

        assert sum(l['receita'] for l in linhas) == metrics.totais(loja, janela)['receita']
```

- [ ] **Step 2: Rodar e confirmar que falha**

Expected: `AttributeError: module 'apps.stores.metrics' has no attribute 'quebra_por'`.

- [ ] **Step 3: Implementar**

Em `apps/stores/metrics/series.py`:

```python
def quebra_por(loja, janela: Janela, campo: str, incluir_teste=False) -> list:
    """Receita do período partida por um campo. Fala de dinheiro.

    Usa a MESMA regra de `totais()` de propósito: somadas, as linhas têm que
    fechar com o total. Uma quebra com regra própria mostra um bolo maior que
    o todo, e aí o dono não sabe em qual dos dois acreditar.

    `campo` aceita travessia do ORM — 'payment_method' ou 'metadata__source'.
    """
    qs = pedidos_de_receita(
        loja=loja, inicio=janela.inicio, fim=janela.fim, incluir_teste=incluir_teste,
    )
    linhas = (
        qs.values(campo)
        .annotate(receita=Sum('total'), pedidos=Count('id'))
        .order_by('-receita')
    )
    return [
        {
            'chave': l[campo] or 'unknown',
            'receita': _decimal(l['receita']),
            'pedidos': l['pedidos'],
        }
        for l in linhas
    ]
```

Exportar em `apps/stores/metrics/__init__.py`: acrescentar `quebra_por` ao import de `.series` e ao `__all__`.

- [ ] **Step 4: Rodar e confirmar que passa**

Expected: PASS, 5 testes.

- [ ] **Step 5: Expor no endpoint de revenue**

Em `apps/stores/api/export_views.py`, no endpoint `revenue`, acrescentar ao payload:

```python
            'por_metodo': metrics.quebra_por(store, janela, 'payment_method'),
            'por_canal': metrics.quebra_por(store, janela, 'metadata__source'),
```

- [ ] **Step 6: Rodar `apps/stores` inteira e commitar**

```bash
git add apps/stores/metrics/series.py apps/stores/metrics/__init__.py apps/stores/api/export_views.py apps/stores/tests/test_quebra_por_metodo_e_canal.py
cat > /tmp/t8.txt <<'MSG'
feat: faturamento por metodo de pagamento e por canal

Usa a MESMA regra de totais(): somadas, as linhas fecham com o total. Uma
quebra com regra propria mostraria um bolo maior que o todo.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
git commit -F /tmp/t8.txt
```

---

### Task 9: Fechamento

- [ ] **Step 1: Suíte completa do backend**

Run: `docker run --rm --network sdd_test_net -e DATABASE_URL=postgres://test:test@pastita_test_db:5432/test -e DJANGO_SETTINGS_MODULE=config.settings.test -e DISABLE_SERVER_SIDE_CURSORS=1 --entrypoint python -v "$PWD":/app -w /app pastita_backend:latest -m pytest apps -q -p no:randomly --ignore=apps/webhooks/tests.py`

Expected: nenhuma falha além das 8 pré-existentes em `apps/postado` (baseline de 14/08). `apps/webhooks/tests.py` tem erro de coleta pré-existente (modelo registrado duas vezes) e fica de fora.

- [ ] **Step 2: Suíte completa do painel**

Run: `cd /home/graco/WORK/pastita-dash && npx jest`

- [ ] **Step 3: Deploy e imagem assada**

```bash
docker restart pastita_web pastita_celery pastita_celery_beat && sleep 25
curl -s -o /dev/null -w "storefront HTTP %{http_code}\n" https://cesaladas.com.br/
docker commit pastita_web pastita_backend:latest
```

- [ ] **Step 4: Conferir os números em produção**

Confirmar, para a Cê Saladas:
- `month.revenue / month.orders` fecha com `metrics.totais(loja, metrics.mes_corrente())`;
- os R$ 306,00 aparecem no faturamento, nas datas de 31/07 e 07/08 (não na de hoje);
- nenhum `payment_method` fora do conjunto fechado.
