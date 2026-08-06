"""O card "Receita hoje" não pode zerar às 21h.

`timezone.now().replace(hour=0, ...)` devolve 00:00 UTC = 21:00 de Brasília do
dia anterior. Efeito: a partir das 21h locais o dia virava em UTC e o
faturamento das 00h às 21h sumia do painel — o pico do delivery inteiro.

O teste congela o relógio às 22h de Brasília (01:00 UTC do dia seguinte) e
cobra que um pedido pago às 12h daquele mesmo dia ainda conte como "hoje".
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.utils import start_of_today
from apps.stores.api.views.order_views import StoreOrderViewSet
from apps.stores.models import Store, StoreOrder

User = get_user_model()
SP = ZoneInfo('America/Sao_Paulo')


class InicioDoDiaLocalTests(TestCase):
    def test_start_of_today_e_meia_noite_local_e_nao_utc(self):
        # 22:00 de Brasília = 01:00 UTC do dia seguinte.
        instante = datetime(2026, 8, 6, 22, 0, tzinfo=SP)
        with timezone.override(SP):
            from unittest.mock import patch
            with patch('django.utils.timezone.now', return_value=instante):
                inicio = start_of_today()

        self.assertEqual(inicio.astimezone(SP).date(), instante.date())
        self.assertEqual(inicio.astimezone(SP).hour, 0)


class ReceitaHojeAs22hTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono-fuso', password='x', email='dono-fuso@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Fuso', slug='loja-fuso', owner=self.owner, status='active',
        )
        # Pedido pago ao meio-dia de Brasília.
        meio_dia = datetime(2026, 8, 6, 12, 0, tzinfo=SP)
        self.pedido = StoreOrder.objects.create(
            store=self.store, customer_name='Cliente', customer_phone='5563999999999',
            customer_email='cli-fuso@real.com',
            subtotal=Decimal('100.00'), total=Decimal('100.00'),
            status=StoreOrder.OrderStatus.DELIVERED,
            payment_status=StoreOrder.PaymentStatus.PAID,
        )
        StoreOrder.objects.filter(pk=self.pedido.pk).update(
            created_at=meio_dia, paid_at=meio_dia,
        )

    def test_venda_do_meio_dia_ainda_conta_as_22h(self):
        from unittest.mock import patch

        vinte_e_duas = datetime(2026, 8, 6, 22, 0, tzinfo=SP)
        rf = APIRequestFactory()
        req = rf.get('/x', {'store': str(self.store.id)})
        force_authenticate(req, user=self.owner)

        with timezone.override(SP):
            with patch('django.utils.timezone.now', return_value=vinte_e_duas):
                resp = StoreOrderViewSet.as_view({'get': 'stats'})(req)

        receita_hoje = Decimal(str(resp.data['revenue']['today']))
        self.assertEqual(
            receita_hoje, Decimal('100.00'),
            'venda do meio-dia sumiu do "hoje" porque o dia virou em UTC às 21h',
        )
