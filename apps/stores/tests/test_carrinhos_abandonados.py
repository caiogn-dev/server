"""Quanto ficou nos carrinhos que não viraram pedido — visível para o dono.

19/09: 51 carrinhos do site com itens, parados entre 1h e 7 dias sem virar
pedido, somavam R$ 7.782,96 — e o painel não mostrava nada. Só 2 eram de
cliente identificado (o resto é visitante sem login), então o valor aqui é o
INDICADOR: quanto, quais produtos, quantos lembretes o sistema já mandou.

Abandonado = carrinho ativo, com itens, parado entre 1 hora e N dias.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCart, StoreCartItem, StoreCategory, StoreProduct

URL = '/api/v1/stores/reports/carrinhos-abandonados/'


class CarrinhosAbandonadosTests(APITestCase):
    def setUp(self):
        self.dono = get_user_model().objects.create_user(username='dono-carr', password='x')
        self.loja = Store.objects.create(name='Loja Carr', slug='loja-carr', owner=self.dono, status='active')
        cat = StoreCategory.objects.create(store=self.loja, name='C', slug='c-carr', is_active=True)
        self.salmao = StoreProduct.objects.create(
            store=self.loja, category=cat, name='Salmão Sublime', slug='salmao-carr',
            price=Decimal('52.90'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        self.frango = StoreProduct.objects.create(
            store=self.loja, category=cat, name='Filé de Frango', slug='frango-carr',
            price=Decimal('39.99'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        self.client.force_authenticate(self.dono)

    def _carrinho(self, horas_parado, itens, cliente=None, metadata=None):
        c = StoreCart.objects.create(
            store=self.loja, session_key=f'k{StoreCart.objects.count()}', user=cliente,
            metadata=metadata or {},
        )
        for produto, qtd in itens:
            StoreCartItem.objects.create(cart=c, product=produto, quantity=qtd)
        StoreCart.objects.filter(pk=c.pk).update(updated_at=timezone.now() - timedelta(hours=horas_parado))
        return c

    def _get(self, **params):
        r = self.client.get(URL, {'store': self.loja.slug, **params})
        assert r.status_code == 200, r.content
        return r.json()

    def test_soma_o_valor_parado_nos_carrinhos(self):
        self._carrinho(3, [(self.salmao, 2)])      # 105,80
        self._carrinho(30, [(self.frango, 1)])     # 39,99

        d = self._get()

        assert d['carrinhos'] == 2
        assert d['valor_total'] == 145.79

    def test_carrinho_de_agora_nao_e_abandono(self):
        """Menos de 1h: a pessoa ainda pode estar escolhendo."""
        self._carrinho(0.2, [(self.salmao, 1)])

        assert self._get()['carrinhos'] == 0

    def test_carrinho_vazio_ou_velho_nao_conta(self):
        self._carrinho(3, [])
        self._carrinho(24 * 10, [(self.salmao, 1)])

        assert self._get()['carrinhos'] == 0

    def test_produtos_mais_abandonados(self):
        self._carrinho(3, [(self.salmao, 1)])
        self._carrinho(4, [(self.salmao, 1), (self.frango, 1)])

        top = self._get()['produtos']

        assert top[0] == {'nome': 'Salmão Sublime', 'carrinhos': 2}

    def test_conta_quem_e_cliente_identificado(self):
        cliente = get_user_model().objects.create_user(username='cli-carr', password='x')
        self._carrinho(3, [(self.salmao, 1)], cliente=cliente)
        self._carrinho(3, [(self.frango, 1)])

        assert self._get()['identificados'] == 1

    def test_conta_lembretes_ja_enviados(self):
        self._carrinho(30, [(self.salmao, 1)], metadata={'reminder_2h_sent': '2026-09-18T10:00:00Z'})

        assert self._get()['com_lembrete'] == 1

    def test_loja_de_outro_dono_e_recusada(self):
        outro = get_user_model().objects.create_user(username='outro-carr', password='x')
        self.client.force_authenticate(outro)

        r = self.client.get(URL, {'store': self.loja.slug})

        assert r.status_code in (403, 404)
