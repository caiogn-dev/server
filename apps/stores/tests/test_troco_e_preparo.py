"""Troco do pagamento em dinheiro + tempo de preparo do pedido.

Troco: o cliente que paga em dinheiro na entrega dizia "troco para R$ 100" na
observação, quando dizia — e o entregador saía sem saber quanto levar. Agora é
coluna do pedido (`change_for`):
- `None`  = ninguém perguntou (PDV, bot, pedido que não é dinheiro);
- `0`     = o cliente disse que NÃO precisa de troco;
- `> 0`   = "troco para" este valor, sempre >= total.

Entrada defensiva: troco ruim (texto, negativo, menor que o total) é
DESCARTADO, nunca derruba a venda.

Preparo: a loja tem um tempo padrão (`Store.default_prep_minutes`); quando o
pedido entra em preparo, esse tempo é FOTOGRAFADO no pedido (`prep_minutes`).
Mudar o padrão depois não mexe na previsão de quem já está no fogo.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.api.serializers import StoreOrderSerializer, StoreSerializer
from apps.stores.models import (
    Store, StoreCart, StoreCartItem, StoreCategory, StoreOrder, StoreProduct,
)
from apps.stores.services.print_service import build_order_print_payload
from apps.stores.services.troco import troco_informado

User = get_user_model()


class TrocoInformadoTests(APITestCase):
    """A regra pura: o que o checkout aceita como troco."""

    def test_so_vale_para_dinheiro(self):
        self.assertIsNone(troco_informado('100', Decimal('35.00'), 'pix'))
        self.assertIsNone(troco_informado('100', Decimal('35.00'), 'card'))

    def test_troco_para_valor_maior_que_o_total(self):
        self.assertEqual(troco_informado('100', Decimal('35.00'), 'cash'), Decimal('100.00'))
        self.assertEqual(troco_informado(50.5, Decimal('35.00'), 'cash'), Decimal('50.50'))
        self.assertEqual(troco_informado('50,50', Decimal('35.00'), 'cash'), Decimal('50.50'))

    def test_valor_igual_ao_total_vale(self):
        self.assertEqual(troco_informado('35', Decimal('35.00'), 'cash'), Decimal('35.00'))

    def test_nao_preciso_de_troco_vira_zero(self):
        self.assertEqual(troco_informado(0, Decimal('35.00'), 'cash'), Decimal('0'))
        self.assertEqual(troco_informado('0', Decimal('35.00'), 'cash'), Decimal('0'))

    def test_nada_informado_fica_none(self):
        self.assertIsNone(troco_informado(None, Decimal('35.00'), 'cash'))
        self.assertIsNone(troco_informado('', Decimal('35.00'), 'cash'))

    def test_lixo_e_descartado_sem_explodir(self):
        for ruim in ('abc', '-10', -10, {'x': 1}, [100], 'NaN', 'inf', True):
            self.assertIsNone(troco_informado(ruim, Decimal('35.00'), 'cash'), ruim)

    def test_menor_que_o_total_e_descartado(self):
        self.assertIsNone(troco_informado('20', Decimal('35.00'), 'cash'))

    def test_valor_absurdo_e_descartado(self):
        self.assertIsNone(troco_informado('999999', Decimal('35.00'), 'cash'))


class _LojaBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-troco', password='x', email='owner-troco@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Troco', slug='loja-troco', owner=self.owner, status='active',
        )

    def _pedido(self, **extra):
        dados = dict(
            store=self.store, customer_name='Cliente', customer_phone='5563999990000',
            customer_email='cli-troco@real.com',
            subtotal=Decimal('35.00'), total=Decimal('35.00'),
        )
        dados.update(extra)
        return StoreOrder.objects.create(**dados)


class TrocoNoPedidoTests(_LojaBase):
    def test_serializer_expoe_troco_e_quanto_levar(self):
        pedido = self._pedido(payment_method='cash', change_for=Decimal('100.00'))
        dados = StoreOrderSerializer(pedido).data
        self.assertEqual(Decimal(dados['change_for']), Decimal('100.00'))
        self.assertEqual(Decimal(dados['change_due']), Decimal('65.00'))

    def test_sem_troco_informado_change_due_none(self):
        dados = StoreOrderSerializer(self._pedido()).data
        self.assertIsNone(dados['change_for'])
        self.assertIsNone(dados['change_due'])

    def test_nao_precisa_de_troco_change_due_zero(self):
        pedido = self._pedido(payment_method='cash', change_for=Decimal('0'))
        self.assertEqual(Decimal(StoreOrderSerializer(pedido).data['change_due']), Decimal('0'))

    def test_troco_nao_e_editavel_pelo_serializer_do_painel(self):
        self.assertIn('change_for', StoreOrderSerializer.Meta.read_only_fields)

    def test_comanda_do_print_agent_leva_o_troco(self):
        pedido = self._pedido(payment_method='cash', change_for=Decimal('100.00'))
        ordem = build_order_print_payload(pedido)['order']
        self.assertEqual(ordem['change_for'], '100.00')
        self.assertEqual(ordem['change_due'], '65.00')

    def test_comanda_sem_troco_informado(self):
        ordem = build_order_print_payload(self._pedido())['order']
        self.assertIsNone(ordem['change_for'])
        self.assertIsNone(ordem['change_due'])


class TrocoNoCheckoutTests(_LojaBase):
    def setUp(self):
        super().setUp()
        categoria = StoreCategory.objects.create(
            store=self.store, name='Cat', slug='cat-troco', is_active=True, sort_order=1,
        )
        produto = StoreProduct.objects.create(
            store=self.store, category=categoria, name='Prato', slug='prato-troco',
            price=Decimal('30.00'), status=StoreProduct.ProductStatus.ACTIVE,
            track_stock=False,
        )
        self.cart_key = 'cart-troco-view'
        cart = StoreCart.objects.create(store=self.store, session_key=self.cart_key)
        StoreCartItem.objects.create(cart=cart, product=produto, quantity=1)

    def _checkout(self, **extra):
        payload = {
            'customer_name': 'Cliente Troco',
            'customer_email': 'cli-troco-view@real.com',
            'customer_phone': '+5563999990000',
            'delivery_method': 'pickup',
            'payment_method': 'cash',
            **extra,
        }
        with patch('apps.stores.services.print_service.enqueue_order_print_job'), \
                patch('apps.stores.services.checkout_service.trigger_order_email_automation'):
            return self.client.post(
                f'/api/v1/stores/{self.store.slug}/checkout/',
                payload, format='json', HTTP_X_CART_KEY=self.cart_key,
            )

    def test_troco_para_100_vai_no_pedido(self):
        resp = self._checkout(change_for='100')
        self.assertEqual(resp.status_code, 201, resp.data)
        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])
        self.assertEqual(pedido.change_for, Decimal('100.00'))

    def test_nao_preciso_de_troco(self):
        resp = self._checkout(change_for=0)
        self.assertEqual(resp.status_code, 201, resp.data)
        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])
        self.assertEqual(pedido.change_for, Decimal('0'))

    def test_troco_ruim_nao_derruba_a_venda(self):
        resp = self._checkout(change_for='cem reais')
        self.assertEqual(resp.status_code, 201, resp.data)
        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])
        self.assertIsNone(pedido.change_for)

    def test_troco_menor_que_o_total_e_descartado_e_a_venda_segue(self):
        resp = self._checkout(change_for='10')
        self.assertEqual(resp.status_code, 201, resp.data)
        pedido = StoreOrder.objects.get(order_number=resp.data['order_number'])
        self.assertIsNone(pedido.change_for)


class TempoDePreparoTests(_LojaBase):
    def test_entrar_em_preparo_fotografa_o_tempo_da_loja(self):
        self.store.default_prep_minutes = 25
        self.store.save(update_fields=['default_prep_minutes'])
        pedido = self._pedido(status='confirmed')
        pedido.update_status('preparing', notify=False)
        pedido.refresh_from_db()
        self.assertEqual(pedido.prep_minutes, 25)

    def test_mudar_o_padrao_depois_nao_mexe_na_previsao(self):
        self.store.default_prep_minutes = 25
        self.store.save(update_fields=['default_prep_minutes'])
        pedido = self._pedido(status='confirmed')
        pedido.update_status('preparing', notify=False)
        Store.objects.filter(pk=self.store.pk).update(default_prep_minutes=60)
        pedido = StoreOrder.objects.get(pk=pedido.pk)
        pedido.internal_notes = 'x'
        pedido.save()
        pedido.refresh_from_db()
        self.assertEqual(pedido.prep_minutes, 25)

    def test_loja_sem_tempo_padrao_nao_tem_previsao(self):
        pedido = self._pedido(status='confirmed')
        pedido.update_status('preparing', notify=False)
        dados = StoreOrderSerializer(StoreOrder.objects.get(pk=pedido.pk)).data
        self.assertIsNone(dados['prep_due_at'])

    def test_pedido_que_nao_entrou_em_preparo_nao_fotografa(self):
        self.store.default_prep_minutes = 25
        self.store.save(update_fields=['default_prep_minutes'])
        pedido = self._pedido(status='confirmed')
        pedido.refresh_from_db()
        self.assertIsNone(pedido.prep_minutes)

    def test_serializer_expoe_a_previsao(self):
        inicio = timezone.now() - timedelta(minutes=10)
        pedido = self._pedido(status='preparing', preparing_at=inicio, prep_minutes=30)
        dados = StoreOrderSerializer(pedido).data
        self.assertEqual(dados['prep_minutes'], 30)
        previsto = timezone.datetime.fromisoformat(dados['prep_due_at'].replace('Z', '+00:00'))
        self.assertAlmostEqual(
            previsto.timestamp(), (inicio + timedelta(minutes=30)).timestamp(), delta=1,
        )

    def test_painel_salva_o_tempo_padrao_da_loja(self):
        s = StoreSerializer(self.store, data={'default_prep_minutes': 40}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        s.save()
        self.store.refresh_from_db()
        self.assertEqual(self.store.default_prep_minutes, 40)

    def test_tempo_padrao_absurdo_e_recusado(self):
        s = StoreSerializer(self.store, data={'default_prep_minutes': 5000}, partial=True)
        self.assertFalse(s.is_valid())
