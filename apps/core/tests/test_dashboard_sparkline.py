"""O overview devolve a série curta de cada KPI, para o mini-gráfico do card.

Um número sozinho não diz se é bom. "R$ 1.557 hoje" pode ser o melhor dia do
mês ou metade do normal, e o comparativo com ontem responde só metade — ontem
pode ter sido atípico. Uma linha de 14 dias responde de relance, sem eixo,
sem legenda e sem ocupar espaço.

Duas decisões que o teste trava:

  - a série usa `serie_completa`, com os dias sem venda preenchidos com ZERO.
    Gráfico com dias faltando mente sobre a tendência: uma semana com venda só
    na sexta vira linha reta se os zeros não estiverem lá.
  - a série respeita a LOJA selecionada, como o resto do overview. Foi
    exatamente o defeito das conversas (208 de três lojas somadas).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreOrder

User = get_user_model()


class DashboardSparklineTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-spark', email='sp@x.com', password='x')
        self.loja = Store.objects.create(
            billing_exempt=True, name='Loja Spark', slug='loja-spark',
            owner=self.owner, status='active',
        )
        self.outra = Store.objects.create(
            billing_exempt=True, name='Outra', slug='outra-spark',
            owner=self.owner, status='active',
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {Token.objects.get_or_create(user=self.owner)[0].key}'
        )

    def _pedido(self, loja, total, dias_atras):
        quando = timezone.now() - timedelta(days=dias_atras)
        p = StoreOrder.objects.create(
            store=loja, total=Decimal(str(total)), subtotal=Decimal(str(total)),
            status=StoreOrder.OrderStatus.DELIVERED,
            payment_status=StoreOrder.PaymentStatus.PAID,
        )
        StoreOrder.objects.filter(pk=p.pk).update(created_at=quando, paid_at=quando)

    def _serie(self, slug):
        r = self.client.get('/api/v1/core/dashboard/overview/', {'store': slug})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()['sparkline']

    def test_devolve_uma_serie_de_14_dias(self):
        self._pedido(self.loja, 100, 1)
        s = self._serie('loja-spark')
        self.assertEqual(len(s['revenue']), 14)
        self.assertEqual(len(s['orders']), 14)

    def test_dia_sem_venda_vira_zero_e_nao_some(self):
        # Série com buracos mente sobre a tendência: uma semana com venda só
        # na sexta viraria uma linha reta.
        self._pedido(self.loja, 100, 3)
        s = self._serie('loja-spark')
        self.assertEqual(len(s['revenue']), 14)
        self.assertIn(0, s['revenue'], 'dias sem venda precisam aparecer como zero')
        self.assertEqual(sum(s['revenue']), 100.0)

    def test_serie_respeita_a_loja_selecionada(self):
        # Mesmo defeito das conversas, que somavam três lojas num numero só.
        self._pedido(self.loja, 100, 1)
        self._pedido(self.outra, 900, 1)
        self.assertEqual(sum(self._serie('loja-spark')['revenue']), 100.0)
        self.assertEqual(sum(self._serie('outra-spark')['revenue']), 900.0)

    def test_loja_sem_venda_devolve_serie_de_zeros_e_nao_lista_vazia(self):
        # Lista vazia faria o card esconder o gráfico e mudar de altura de uma
        # loja para outra. Zeros desenham a linha rente ao chão, que é a verdade.
        s = self._serie('loja-spark')
        self.assertEqual(len(s['revenue']), 14)
        self.assertEqual(set(s['revenue']), {0})

    def test_pedidos_contam_unidades_nao_dinheiro(self):
        self._pedido(self.loja, 100, 1)
        self._pedido(self.loja, 50, 1)
        s = self._serie('loja-spark')
        self.assertEqual(sum(s['orders']), 2)
