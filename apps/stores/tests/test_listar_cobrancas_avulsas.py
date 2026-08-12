"""Listar as cobranças avulsas de uma loja.

A tela "Link de pagamento" guardava o link gerado só no estado do React: um F5
e o lojista perdia o link, sem nenhum lugar para consultar depois nem para
saber se o cliente pagou. Em produção havia 14 cobranças avulsas (algumas
pagas, várias pendentes) que a tela nunca mostrou.

O queryset já enxergava as avulsas; faltava (a) poder pedir SÓ elas e (b) o
serializer de lista devolver link, rótulo e pagador — sem isso a tela mostra
uma pilha de valores sem identidade.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreOrder, StorePayment

User = get_user_model()


class ListarCobrancasAvulsasTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-cob', password='x')
        self.store = Store.objects.create(
            name='Loja Cob', slug='loja-cob', owner=self.dono, status='active',
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.dono).key}',
        )

    def _avulsa(self, amount='50.00', status=StorePayment.PaymentStatus.PENDING, descricao=None):
        return StorePayment.objects.create(
            store=self.store, order=None, amount=Decimal(amount), status=status,
            payment_method=StorePayment.PaymentMethod.OTHER,
            payment_url='https://mp.example/checkout/abc',
            payer_name='Fulano',
            metadata=({'description': descricao} if descricao else {}),
        )

    def _de_pedido(self):
        order = StoreOrder.objects.create(
            store=self.store, subtotal=Decimal('80.00'), total=Decimal('80.00'),
        )
        return StorePayment.objects.create(
            store=self.store, order=order, amount=Decimal('80.00'),
            status=StorePayment.PaymentStatus.COMPLETED,
            payment_method=StorePayment.PaymentMethod.PIX,
        )

    def test_sem_pedido_traz_so_as_avulsas(self):
        avulsa = self._avulsa()
        self._de_pedido()

        r = self.client.get('/api/v1/stores/payments/', {
            'store': str(self.store.id), 'sem_pedido': '1',
        })

        self.assertEqual(r.status_code, 200)
        ids = [p['id'] for p in r.data['results']]
        self.assertEqual(ids, [str(avulsa.id)])

    def test_sem_o_filtro_a_listagem_nao_muda(self):
        self._avulsa()
        self._de_pedido()

        r = self.client.get('/api/v1/stores/payments/', {'store': str(self.store.id)})

        self.assertEqual(len(r.data['results']), 2)

    def test_lista_traz_link_rotulo_e_pagador(self):
        """Sem esses campos a tela é uma pilha de valores sem identidade."""
        self._avulsa(descricao='Sinal do evento')

        r = self.client.get('/api/v1/stores/payments/', {
            'store': str(self.store.id), 'sem_pedido': '1',
        })

        item = r.data['results'][0]
        self.assertEqual(item['payment_url'], 'https://mp.example/checkout/abc')
        self.assertEqual(item['payer_name'], 'Fulano')
        self.assertEqual(item['description'], 'Sinal do evento')

    def test_cobranca_de_outra_loja_nao_vaza(self):
        outro = User.objects.create_user(username='vizinho-cob', password='x')
        alheia = Store.objects.create(
            name='Alheia Cob', slug='alheia-cob', owner=outro, status='active',
        )
        StorePayment.objects.create(
            store=alheia, order=None, amount=Decimal('999.00'),
            status=StorePayment.PaymentStatus.PENDING,
            payment_method=StorePayment.PaymentMethod.OTHER,
        )
        minha = self._avulsa()

        r = self.client.get('/api/v1/stores/payments/', {'sem_pedido': '1'})

        ids = [p['id'] for p in r.data['results']]
        self.assertEqual(ids, [str(minha.id)])
