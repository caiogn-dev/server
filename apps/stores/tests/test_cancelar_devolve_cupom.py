"""Pedido que morre devolve o que reservou — pelos três caminhos de cancelar.

Casos de produção (medido em 15/set): CE-2609102194, CE-2608245229,
CE-2608225494 e CE-2608129383, vendas em dinheiro canceladas pelo painel, nunca
devolveram a vaga do cupom. Só o webhook do Mercado Pago chamava
`_release_coupon`; o botão de cancelar (`cancel_order`) e o dropdown de status
(`update_status`) não. E a expiração de PIX de 24h cancelava com `.update()`
cru, sem passar por nenhum dos dois.

O limite por cliente e o de primeira compra já ignoram pedido cancelado; quem
fica errado é o `used_count` global, que esgota um cupom com `usage_limit`
antes da hora.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.stores.models import Store, StoreCoupon, StoreOrder
from apps.stores.services.order_service import OrderService

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono_cupom_cancel', password='x')
    return Store.objects.create(owner=dono, name='Loja Cupom', slug='loja-cupom-cancel')


@pytest.fixture
def cupom(loja):
    agora = timezone.now()
    return StoreCoupon.objects.create(
        store=loja, code='SALADA10', discount_value=Decimal('10'),
        usage_limit=100, used_count=1,
        valid_from=agora - timedelta(days=1), valid_until=agora + timedelta(days=30),
    )


def _pedido(loja, **extra):
    campos = dict(
        store=loja, total=Decimal('85.50'), subtotal=Decimal('95.00'),
        discount=Decimal('9.50'), coupon_code='SALADA10',
        status='confirmed', payment_status='paid', payment_method='cash',
    )
    campos.update(extra)
    return StoreOrder.objects.create(**campos)


@pytest.mark.django_db
class TestCancelarDevolveCupom:

    def test_botao_de_cancelar_devolve_a_vaga(self, loja, cupom):
        pedido = _pedido(loja)

        OrderService().cancel_order(pedido, restore_stock=False)

        cupom.refresh_from_db()
        assert cupom.used_count == 0

    def test_dropdown_de_status_devolve_a_vaga(self, loja, cupom):
        pedido = _pedido(loja)

        OrderService().update_status(pedido, 'cancelled', notify_customer=False)

        cupom.refresh_from_db()
        assert cupom.used_count == 0

    def test_devolve_uma_vez_so(self, loja, cupom):
        """Webhook do MP já devolveu e depois o operador cancela: não devolve de novo."""
        cupom.used_count = 2
        cupom.save(update_fields=['used_count'])
        pedido = _pedido(loja, metadata={'coupon_released': True})

        OrderService().cancel_order(pedido, restore_stock=False)

        cupom.refresh_from_db()
        assert cupom.used_count == 2


@pytest.mark.django_db
class TestPixVencido:

    def _rodar_tarefa(self):
        from apps.whatsapp.tasks import automation_tasks
        with patch.object(automation_tasks.send_payment_reminder, 'delay'):
            automation_tasks.check_pending_payments()

    def test_pix_de_24h_cancela_pelo_servico(self, loja, cupom):
        pedido = _pedido(loja, status='pending', payment_status='pending', payment_method='pix')
        StoreOrder.objects.filter(id=pedido.id).update(created_at=timezone.now() - timedelta(hours=25))

        self._rodar_tarefa()

        pedido.refresh_from_db()
        cupom.refresh_from_db()
        assert pedido.status == 'cancelled'
        assert pedido.cancelled_at is not None
        assert pedido.payment_status not in ('pending', 'paid')
        assert cupom.used_count == 0

    def test_pix_recente_fica_como_esta(self, loja, cupom):
        pedido = _pedido(loja, status='pending', payment_status='pending', payment_method='pix')

        self._rodar_tarefa()

        pedido.refresh_from_db()
        assert pedido.status == 'pending'


@pytest.mark.django_db
class TestNumeroDoPedidoQueColide:

    def test_sorteia_de_novo_quando_o_numero_ja_existe(self, loja):
        existente = _pedido(loja, coupon_code='', discount=Decimal('0'))
        with patch.object(
            StoreOrder, 'generate_order_number',
            side_effect=[existente.order_number, 'LOJ2609150001'],
        ):
            novo = _pedido(loja, coupon_code='', discount=Decimal('0'))

        assert novo.order_number == 'LOJ2609150001'
        assert StoreOrder.objects.filter(store=loja).count() == 2

    def test_numero_informado_nao_e_trocado_em_silencio(self, loja):
        """Quem passou `order_number` explícito continua recebendo o erro."""
        from django.db import IntegrityError, transaction
        existente = _pedido(loja, coupon_code='', discount=Decimal('0'))
        with pytest.raises(IntegrityError), transaction.atomic():
            _pedido(loja, coupon_code='', discount=Decimal('0'), order_number=existente.order_number)
