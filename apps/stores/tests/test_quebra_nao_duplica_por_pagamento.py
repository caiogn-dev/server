"""Duas tentativas de PIX no mesmo pedido não podem virar duas vendas.

Bug relatado pelo dono em 17/set/2026: na Cê Saladas, "Como entrou o dinheiro"
mostrava PIX R$ 5.616,49 em 81 pedidos enquanto o faturamento do mesmo recorte
era R$ 4.626,75 — e as três linhas da quebra somavam 96 pedidos num período com
81 pedidos faturados. Cartão e dinheiro batiam; só o PIX inflava.

Causa: `StoreOrderViewSet.get_queryset` anota `amount_paid_agg` com
`Sum('payments__amount')`, o que acrescenta um LEFT JOIN em `store_payments`.
`quebra_de_lista` faz `.values(campo).annotate(Count/Sum)` sobre esse queryset,
e o reagrupamento passa a contar UMA LINHA POR REGISTRO DE PAGAMENTO: pedido
com 2 tentativas de PIX (pendente + aprovada) conta 2 vezes, com o `total`
somado 2 vezes. Eram 11 pedidos com pagamento repetido = 15 linhas extras =
R$ 1.282,40 inflados.

A quebra existe para conferir a gaveta e o extrato do gateway. Inflada, ela
manda o dono procurar um dinheiro que nunca entrou.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores import metrics
from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


def _pedido_pago(loja, **extra):
    dados = dict(
        store=loja, customer_name='Cliente', customer_phone='5563999000001',
        subtotal=Decimal('60.00'), delivery_fee=Decimal('10.00'), total=Decimal('70.00'),
        payment_status='paid', status='delivered', paid_at=timezone.now(),
        payment_method='pix', source='web', is_active=True,
    )
    dados.update(extra)
    return StoreOrder.objects.create(**dados)


def _tentativas_de_pix(pedido, quantas):
    """Simula o que o Mercado Pago grava: uma cobrança pendente e a aprovada."""
    for i in range(quantas):
        StorePayment.objects.create(
            order=pedido, store=pedido.store, amount=pedido.total,
            payment_method='pix',
            status='completed' if i == quantas - 1 else 'pending',
        )


class QuebraNaoDuplicaPorPagamentoTests(TestCase):
    """O núcleo: a quebra é imune a joins trazidos pelo queryset da view."""

    def setUp(self):
        self.dono = User.objects.create_user(username='dono-quebra', password='x', email='dq@real.com')
        self.loja = Store.objects.create(
            name='Loja Quebra', slug='loja-quebra', owner=self.dono, status='active',
        )
        self.pedido = _pedido_pago(self.loja)
        _tentativas_de_pix(self.pedido, 2)

    def _queryset_como_a_view(self):
        """Reproduz o annotate `amount_paid_agg` que a view aplica (LEFT JOIN)."""
        from django.db.models import DecimalField, Q, Sum
        from django.db.models.functions import Coalesce

        return StoreOrder.objects.filter(store=self.loja).annotate(
            amount_paid_agg=Coalesce(
                Sum('payments__amount', filter=Q(payments__status='completed')),
                Decimal('0.00'),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )

    def test_um_pedido_com_duas_cobrancas_conta_uma_vez(self):
        (linha,) = metrics.quebra_de_lista(self._queryset_como_a_view(), 'payment_method')
        self.assertEqual(linha['pedidos'], 1)
        self.assertEqual(linha['total'], Decimal('70.00'))

    def test_quebra_por_canal_tambem_nao_duplica(self):
        (linha,) = metrics.quebra_de_lista(self._queryset_como_a_view(), 'source')
        self.assertEqual(linha['pedidos'], 1)
        self.assertEqual(linha['total'], Decimal('70.00'))

    def test_partes_somam_faturamento_mais_frete(self):
        """A régua que o painel promete: quebra = faturamento + frete."""
        qs = self._queryset_como_a_view()
        resumo = metrics.resumo_de_lista(qs)
        soma = sum(l['total'] for l in metrics.quebra_de_lista(qs, 'payment_method'))
        self.assertEqual(soma, resumo['receita'] + resumo['frete'])

    def test_pedidos_da_quebra_somam_os_faturados(self):
        qs = self._queryset_como_a_view()
        resumo = metrics.resumo_de_lista(qs)
        n = sum(l['pedidos'] for l in metrics.quebra_de_lista(qs, 'payment_method'))
        self.assertEqual(n, resumo['pedidos_faturados'])


class ResumoDoHistoricoNaoDuplicaTests(APITestCase):
    """O endpoint que o painel chama, com o cenário exato do relato."""

    def setUp(self):
        cache.clear()
        self.dono = User.objects.create_superuser(
            username='dono-quebra-api', password='x', email='dqa@real.com',
        )
        self.loja = Store.objects.create(
            name='Loja Quebra API', slug='loja-quebra-api', owner=self.dono,
            status='active', billing_exempt=True,
        )
        # Um PIX com duas tentativas, um PIX com uma, um dinheiro sem nenhuma.
        _tentativas_de_pix(_pedido_pago(self.loja), 2)
        _tentativas_de_pix(_pedido_pago(self.loja), 1)
        _pedido_pago(self.loja, payment_method='cash')
        self.client.force_authenticate(self.dono)

    def test_quebra_do_endpoint_bate_com_o_faturamento(self):
        r = self.client.get('/api/v1/stores/orders/resumo/', {'store': self.loja.slug})
        self.assertEqual(r.status_code, 200, r.content)

        por_pagamento = {l['chave']: l for l in r.data['por_pagamento']}
        self.assertEqual(por_pagamento['pix']['pedidos'], 2)
        self.assertEqual(por_pagamento['pix']['total'], '140.00')
        self.assertEqual(por_pagamento['cash']['pedidos'], 1)
        self.assertEqual(por_pagamento['cash']['total'], '70.00')

        # 3 pedidos × R$ 60 de venda = 180; frete 3 × 10 = 30; quebra = 210.
        self.assertEqual(r.data['faturamento'], '180.00')
        self.assertEqual(r.data['frete'], '30.00')
        self.assertEqual(
            sum(Decimal(l['total']) for l in r.data['por_pagamento']),
            Decimal(r.data['faturamento']) + Decimal(r.data['frete']),
        )
        self.assertEqual(
            sum(l['pedidos'] for l in r.data['por_pagamento']),
            r.data['pedidos_faturados'],
        )
