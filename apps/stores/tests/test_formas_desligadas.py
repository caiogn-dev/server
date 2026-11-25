"""Formas de pagamento ligadas/desligadas pelo lojista (25/11, Ivoneth).

O cardápio oferecia tudo que estava conectado (PIX/cartão pelo Mercado Pago,
vale, dinheiro/maquininha) e o dono não tinha como tirar uma forma sem
desconectar o gateway. Agora: Configurações → Pagamentos lista as formas que o
cardápio pode oferecer, cada uma com interruptor (`metadata.formas_desligadas`).

Desligada some da config pública E o checkout recusa — o cardápio antigo em
cache não cria pedido com forma que o dono tirou.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from apps.stores.api.views.storefront_views import build_store_payment_config
from apps.stores.formas_de_pagamento import forma_desligada
from apps.stores.models import (
    Store, StoreCart, StoreCartItem, StoreCategory, StoreOrder, StoreProduct,
)

User = get_user_model()


class _Base(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-fd', email='d@fd.com', password='x')
        self.store = Store.objects.create(
            name='Loja FD', slug='loja-fd', owner=self.dono, status='active',
        )

    def _desligar(self, *formas):
        self.store.metadata = {**(self.store.metadata or {}), 'formas_desligadas': list(formas)}
        self.store.save(update_fields=['metadata'])


class RegraTests(_Base):
    def test_nada_desligado_por_padrao(self):
        self.assertFalse(forma_desligada(self.store, 'cash'))

    def test_cartao_tem_varios_nomes(self):
        self._desligar('credit_card')
        for nome in ('card', 'credit_card', 'debit_card'):
            self.assertTrue(forma_desligada(self.store, nome), nome)
        self.assertFalse(forma_desligada(self.store, 'pix'))

    def test_config_publica_tira_a_desligada(self):
        self.assertIn('cash', build_store_payment_config(self.store)['enabled_methods'])
        self._desligar('cash')
        metodos = build_store_payment_config(self.store)['enabled_methods']
        self.assertNotIn('cash', metodos)
        self.assertIn('card_on_delivery', metodos)


class PainelTests(_Base):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.dono)
        self.url = f'/api/v1/stores/stores/{self.store.id}/formas-de-pagamento/'

    def test_lista_as_formas_com_disponivel_e_ligada(self):
        self._desligar('cash')
        r = self.api.get(self.url)
        self.assertEqual(r.status_code, 200, r.data)
        por_metodo = {f['metodo']: f for f in r.data['formas']}
        # Ordem e catálogo fixos: o dono vê as 6 sempre, mesmo sem gateway.
        self.assertEqual(
            [f['metodo'] for f in r.data['formas']],
            ['pix', 'credit_card', 'cash', 'card_on_delivery', 'voucher', 'voucher_link'],
        )
        self.assertTrue(por_metodo['cash']['disponivel'])
        self.assertFalse(por_metodo['cash']['ligada'])
        self.assertTrue(por_metodo['card_on_delivery']['ligada'])
        # Sem Mercado Pago conectado: PIX não está disponível (não há o que ligar).
        self.assertFalse(por_metodo['pix']['disponivel'])
        self.assertTrue(por_metodo['pix']['rotulo'])

    def test_patch_grava_e_preserva_o_resto_do_metadata(self):
        self.store.metadata = {'perguntar_ocasiao': True}
        self.store.save(update_fields=['metadata'])
        r = self.api.patch(self.url, {'desligadas': ['cash', 'pix']}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.metadata['formas_desligadas'], ['pix', 'cash'])
        self.assertTrue(self.store.metadata['perguntar_ocasiao'])

    def test_patch_vazio_remove_a_chave(self):
        self._desligar('cash')
        r = self.api.patch(self.url, {'desligadas': []}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.store.refresh_from_db()
        self.assertNotIn('formas_desligadas', self.store.metadata)

    def test_forma_inventada_recusada(self):
        r = self.api.patch(self.url, {'desligadas': ['bitcoin']}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_outra_loja_nao_mexe(self):
        intruso = User.objects.create_user(username='intruso-fd', email='i@fd.com', password='x')
        api = APIClient()
        api.force_authenticate(intruso)
        self.assertEqual(api.patch(self.url, {'desligadas': ['cash']}, format='json').status_code, 404)


class CheckoutTests(_Base):
    def setUp(self):
        super().setUp()
        categoria = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-fd', is_active=True, sort_order=1,
        )
        produto = StoreProduct.objects.create(
            store=self.store, category=categoria, name='Item FD', slug='item-fd',
            price=Decimal('30.00'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        self.cart_key = 'cart-fd'
        cart = StoreCart.objects.create(store=self.store, session_key=self.cart_key)
        StoreCartItem.objects.create(cart=cart, product=produto, quantity=1)

    def _checkout(self, metodo):
        with patch('apps.stores.services.print_service.enqueue_order_print_job'), \
                patch('apps.stores.services.checkout_service.trigger_order_email_automation'):
            return self.client.post(
                f'/api/v1/stores/{self.store.slug}/checkout/',
                {
                    'customer_name': 'Cliente FD', 'customer_email': 'cli-fd@real.com',
                    'customer_phone': '+5563999990002', 'delivery_method': 'pickup',
                    'payment_method': metodo,
                },
                format='json', HTTP_X_CART_KEY=self.cart_key,
            )

    def test_forma_desligada_recusada_sem_criar_pedido(self):
        self._desligar('cash')
        r = self._checkout('cash')
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn('Dinheiro', str(r.data))
        self.assertFalse(StoreOrder.objects.filter(store=self.store).exists())

    def test_forma_ligada_segue(self):
        self._desligar('pix')
        self.assertEqual(self._checkout('cash').status_code, 201)
