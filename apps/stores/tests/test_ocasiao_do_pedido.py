"""Ocasião do pedido (03/11, sugestão do atendente da Ivoneth).

Loja de encomenda e coffee break precisa saber PARA QUÊ é o pedido: um coffee
de 30 pessoas para reunião de firma e o mesmo coffee para o aniversário de 60
anos da mãe pedem capricho diferente. A pergunta é opcional e só aparece na
loja que ligar (`metadata.perguntar_ocasiao`). Na Cê Saladas, que vende
almoço, ela seria ruído.

A resposta vai para `order.metadata['ocasiao']` e sai na faixa "ATENCAO DA
LOJA" da comanda — a única que todo print agent instalado imprime.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from apps.stores.models import (
    Store, StoreCart, StoreCartItem, StoreCategory, StoreOrder, StoreProduct,
)
from apps.stores.services import ocasiao
from apps.stores.services.print_service import build_order_print_payload

User = get_user_model()


class _Base(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-oc', email='d@oc.com', password='x')
        self.store = Store.objects.create(
            name='Banqueteria OC', slug='banq-oc', owner=self.dono, status='active',
        )

    def _ligar(self, ligado=True):
        self.store.metadata = {**(self.store.metadata or {}), 'perguntar_ocasiao': ligado}
        self.store.save(update_fields=['metadata'])


class RegraTests(_Base):
    def test_opcoes_tem_valor_e_rotulo_sem_emoji(self):
        opcoes = ocasiao.opcoes()
        valores = [o['valor'] for o in opcoes]
        self.assertIn('aniversario', valores)
        self.assertIn('meu_aniversario', valores)
        self.assertIn('reuniao', valores)
        self.assertIn('casamento', valores)
        self.assertEqual(valores[-1], 'outro')
        for o in opcoes:
            self.assertTrue(o['rotulo'])
            self.assertTrue(all(ord(c) < 0x2000 for c in o['rotulo']), o['rotulo'])

    def test_loja_desligada_nao_pergunta_e_descarta(self):
        self.assertFalse(ocasiao.pergunta_ligada(self.store))
        self.assertEqual(ocasiao.ocasiao_valida(self.store, 'casamento'), '')

    def test_loja_ligada_aceita_so_valor_conhecido(self):
        self._ligar()
        self.assertTrue(ocasiao.pergunta_ligada(self.store))
        self.assertEqual(ocasiao.ocasiao_valida(self.store, 'casamento'), 'casamento')
        self.assertEqual(ocasiao.ocasiao_valida(self.store, ' Casamento '), 'casamento')
        for ruim in ('', None, 'festa da firma', 123, {'x': 1}, ['casamento']):
            self.assertEqual(ocasiao.ocasiao_valida(self.store, ruim), '', ruim)

    def test_texto_da_comanda_sem_acento(self):
        self.assertEqual(ocasiao.para_comanda('casamento'), 'OCASIAO: Casamento')
        self.assertIn('proprio cliente', ocasiao.para_comanda('meu_aniversario'))
        self.assertEqual(ocasiao.para_comanda(''), '')
        self.assertEqual(ocasiao.para_comanda('inventada'), '')


class AppConfigTests(_Base):
    def test_desligada_manda_perguntar_false(self):
        r = APIClient().get(f'/api/v1/stores/{self.store.slug}/app-config/')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data['ocasiao']['perguntar'])

    def test_ligada_manda_as_opcoes(self):
        self._ligar()
        r = APIClient().get(f'/api/v1/stores/{self.store.slug}/app-config/')
        self.assertTrue(r.data['ocasiao']['perguntar'])
        self.assertEqual(r.data['ocasiao']['opcoes'], ocasiao.opcoes())


class PainelTests(_Base):
    def test_dono_liga_sem_apagar_o_resto_do_metadata(self):
        self.store.metadata = {'agendamento': {'intervalo': 90}}
        self.store.save(update_fields=['metadata'])
        api = APIClient()
        api.force_authenticate(self.dono)
        r = api.patch(f'/api/v1/stores/stores/{self.store.slug}/', {'perguntar_ocasiao': True}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data['perguntar_ocasiao'])
        self.store.refresh_from_db()
        self.assertTrue(self.store.metadata['perguntar_ocasiao'])
        self.assertEqual(self.store.metadata['agendamento'], {'intervalo': 90})

        r = api.patch(f'/api/v1/stores/stores/{self.store.slug}/', {'perguntar_ocasiao': False}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.store.refresh_from_db()
        self.assertNotIn('perguntar_ocasiao', self.store.metadata)

    def test_patch_sem_o_campo_nao_mexe(self):
        self._ligar()
        api = APIClient()
        api.force_authenticate(self.dono)
        r = api.patch(f'/api/v1/stores/stores/{self.store.slug}/', {'name': 'Banq Nova'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.store.refresh_from_db()
        self.assertTrue(self.store.metadata['perguntar_ocasiao'])


class CheckoutTests(_Base):
    def setUp(self):
        super().setUp()
        categoria = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-oc', is_active=True, sort_order=1,
        )
        produto = StoreProduct.objects.create(
            store=self.store, category=categoria, name='Coffee 30', slug='coffee-oc',
            price=Decimal('30.00'), status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
        )
        self.cart_key = 'cart-ocasiao'
        cart = StoreCart.objects.create(store=self.store, session_key=self.cart_key)
        StoreCartItem.objects.create(cart=cart, product=produto, quantity=1)

    def _checkout(self, **extra):
        payload = {
            'customer_name': 'Cliente Ocasiao',
            'customer_email': 'cli-oc@real.com',
            'customer_phone': '+5563999990001',
            'delivery_method': 'pickup',
            'payment_method': 'cash',
            **extra,
        }
        with patch('apps.stores.services.print_service.enqueue_order_print_job'), \
                patch('apps.stores.services.checkout_service.trigger_order_email_automation'):
            r = self.client.post(
                f'/api/v1/stores/{self.store.slug}/checkout/',
                payload, format='json', HTTP_X_CART_KEY=self.cart_key,
            )
        self.assertEqual(r.status_code, 201, r.data)
        return StoreOrder.objects.get(order_number=r.data['order_number'])

    def test_loja_ligada_grava_a_ocasiao(self):
        self._ligar()
        pedido = self._checkout(ocasiao='casamento')
        self.assertEqual(pedido.metadata.get('ocasiao'), 'casamento')

    def test_loja_desligada_ignora(self):
        pedido = self._checkout(ocasiao='casamento')
        self.assertNotIn('ocasiao', pedido.metadata)

    def test_valor_inventado_nao_derruba_a_venda(self):
        self._ligar()
        pedido = self._checkout(ocasiao='<script>')
        self.assertNotIn('ocasiao', pedido.metadata)

    def test_sem_resposta_segue_normal(self):
        self._ligar()
        pedido = self._checkout()
        self.assertNotIn('ocasiao', pedido.metadata)


class ComandaTests(_Base):
    def _pedido(self, **campos):
        dados = dict(
            store=self.store, customer_name='Cliente', customer_phone='63999990000',
            subtotal=Decimal('30'), total=Decimal('30'), delivery_method='pickup',
            payment_method='pix', payment_status='paid', status='confirmed',
        )
        dados.update(campos)
        return StoreOrder.objects.create(**dados)

    def test_comanda_mostra_a_ocasiao(self):
        notas = build_order_print_payload(self._pedido(metadata={'ocasiao': 'casamento'}))['order']['internal_notes']
        self.assertIn('OCASIAO: Casamento', notas)

    def test_ocasiao_junto_com_nota_e_maquininha(self):
        pedido = self._pedido(
            metadata={'ocasiao': 'reuniao'}, internal_notes='Entregar na portaria',
            payment_method='card_on_delivery', payment_status='pending',
        )
        notas = build_order_print_payload(pedido)['order']['internal_notes']
        self.assertTrue(notas.startswith('LEVAR MAQUININHA'), notas)
        self.assertIn('OCASIAO: Reuniao', notas)
        self.assertIn('Entregar na portaria', notas)

    def test_sem_ocasiao_comanda_igual(self):
        notas = build_order_print_payload(self._pedido(internal_notes='x'))['order']['internal_notes']
        self.assertEqual(notas, 'x')
