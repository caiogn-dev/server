"""Pedido da 99Food entrando no Cardapidex e o painel mandando o status de volta.

Contrato lido em developer-food.99app.com (03/11/2026), "Order Webhooks",
"Get Order Details", "Confirm/Ready/Delivered/Cancel Order", "Get Authtoken":

- `orderNew` chega com o pedido inteiro; a loja tem 5 min para confirmar ou a
  99 cancela sozinha;
- preço sempre inteiro em centavos;
- `delivery_type` 0 = cliente retira, 1 = entregador da 99, 2 = entrega da loja;
- ações são POST em openapi.99food.com/v1/order/order/<acao> com auth_token da
  loja; token vem de GET /v1/auth/authtoken/get (app_id, app_secret, app_shop_id).
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.stores.services import pedidos_da_99 as p99

User = get_user_model()
PEDIDO = 5764625173055605353


def _pedido_novo(**mudancas):
    info = {
        'order_id': PEDIDO, 'status': 100, 'order_index': 7, 'remark': 'sem cebola',
        'pay_type': 1, 'pay_method': 1, 'pay_channel': 150, 'change_for': 0,
        'delivery_type': 2, 'fulfillment_mode': 0, 'need_cutlery': True,
        'handover_code': '5000',
        'price': {
            'order_price': 5980, 'items_discount': 500, 'delivery_price': 700,
            'delivery_discount': 0, 'real_pay_price': 6180,
            'customer_need_paying_money': 0,
        },
        'shop': {'app_shop_id': 'loja-99'},
        'receive_address': {
            'name': 'João Silva', 'first_name': 'João', 'last_name': 'Silva',
            'calling_code': '+55', 'phone': '00016007722',
            'street_name': 'Quadra 104 Norte', 'street_number': '12',
            'district': 'Plano Diretor Norte', 'city': 'Palmas', 'state': 'TO',
            'postal_code': '77006-000', 'complement': 'apto 3', 'reference': 'perto da praça',
            'poi_address': 'Quadra 104 Norte, 12 - Palmas', 'poi_lat': -10.17, 'poi_lng': -48.33,
            'virtual_phone_number': '06234421637', 'locator': '56244631',
        },
        'order_items': [
            {'app_item_id': '', 'name': 'Salada Queridinha', 'sku_price': 2990, 'total_price': 5980,
             'amount': 2, 'remark': 'molho à parte',
             'sub_item_list': [
                 {'name': 'Molho de mostarda', 'sku_price': 0, 'amount': 1, 'sub_item_list': []},
                 {'name': 'Ovo extra', 'sku_price': 0, 'amount': 2, 'sub_item_list': []},
             ]},
        ],
    }
    info.update(mudancas)
    return {'order_id': PEDIDO, 'order_info': info}


@override_settings(NINETY_NINE_APP_ID='1152921557674426642', NINETY_NINE_APP_SECRET='segredo')
class Base(TestCase):
    def setUp(self):
        cache.clear()
        dono = User.objects.create_user(username='dono99', password='x')
        self.store = Store.objects.create(
            name='Loja 99', slug='loja-99', owner=dono, status='active')


class LojaDoAvisoTests(Base):
    def test_acha_pelo_slug(self):
        self.assertEqual(p99.loja_do_aviso('loja-99'), self.store)

    def test_acha_pelo_codigo_gravado_na_loja(self):
        self.store.metadata = {'app_shop_id_99': 'X7'}
        self.store.save()
        self.assertEqual(p99.loja_do_aviso('X7'), self.store)

    def test_codigo_desconhecido_nao_acha(self):
        self.assertIsNone(p99.loja_do_aviso('nao-existe'))
        self.assertIsNone(p99.loja_do_aviso(''))


@mock.patch('apps.stores.services.pedidos_da_99.confirmar_depois')
@mock.patch('apps.stores.services.pedidos_da_99.imprimir_depois')
class PedidoNovoTests(Base):
    def test_vira_pedido_da_loja_com_valores_em_reais(self, _imp, _conf):
        with self.captureOnCommitCallbacks(execute=True):
            pedido, criado = p99.receber_pedido_novo(self.store, _pedido_novo())
        self.assertTrue(criado)
        pedido.refresh_from_db()
        self.assertEqual(pedido.store, self.store)
        self.assertEqual(pedido.source, '99food')
        self.assertEqual(pedido.subtotal, Decimal('59.80'))
        self.assertEqual(pedido.discount, Decimal('5.00'))
        self.assertEqual(pedido.delivery_fee, Decimal('7.00'))
        self.assertEqual(pedido.total, Decimal('61.80'))
        self.assertEqual(pedido.customer_name, 'João Silva')
        self.assertEqual(pedido.delivery_method, 'delivery')
        self.assertEqual(pedido.delivery_address['street'], 'Quadra 104 Norte')
        self.assertEqual(pedido.delivery_address['neighborhood'], 'Plano Diretor Norte')
        self.assertEqual(pedido.customer_notes, 'sem cebola')
        # O pedido é da 99: o aviso de status ao cliente é dela, não nosso.
        self.assertTrue(pedido.metadata['suppress_notifications'])
        self.assertEqual(pedido.metadata['99food']['order_id'], str(PEDIDO))
        self.assertEqual(pedido.metadata['99food']['numero'], 7)

    def test_pago_no_app_ja_nasce_pago(self, _imp, _conf):
        pedido, _ = p99.receber_pedido_novo(self.store, _pedido_novo())
        self.assertEqual(pedido.payment_status, 'paid')

    def test_dinheiro_na_entrega_fica_a_receber_com_troco(self, _imp, _conf):
        pedido, _ = p99.receber_pedido_novo(
            self.store, _pedido_novo(pay_type=2, pay_method=2, pay_channel=153, change_for=10000))
        self.assertEqual(pedido.payment_method, 'cash')
        self.assertEqual(pedido.payment_status, 'pending')
        self.assertEqual(pedido.change_for, Decimal('100.00'))

    def test_itens_com_adicionais_e_observacao(self, _imp, _conf):
        pedido, _ = p99.receber_pedido_novo(self.store, _pedido_novo())
        item = pedido.items.get()
        self.assertEqual(item.product_name, 'Salada Queridinha')
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal('29.90'))
        self.assertEqual(item.subtotal, Decimal('59.80'))
        self.assertEqual(item.variant_name, 'Molho de mostarda, 2x Ovo extra')
        self.assertEqual(item.notes, 'molho à parte')

    def test_item_liga_ao_produto_quando_o_codigo_bate(self, _imp, _conf):
        produto = StoreProduct.objects.create(
            store=self.store, name='Queridinha', slug='queridinha', price=Decimal('29.90'))
        dados = _pedido_novo()
        dados['order_info']['order_items'][0]['app_item_id'] = str(produto.id)
        pedido, _ = p99.receber_pedido_novo(self.store, dados)
        self.assertEqual(pedido.items.get().product, produto)

    def test_retirada_e_entrega_da_99(self, _imp, _conf):
        retirada, _ = p99.receber_pedido_novo(
            self.store, _pedido_novo(fulfillment_mode=1, delivery_type=0))
        self.assertEqual(retirada.delivery_method, 'pickup')
        retirada.delete()
        da_99, _ = p99.receber_pedido_novo(self.store, _pedido_novo(delivery_type=1))
        self.assertEqual(da_99.external_delivery_provider, '99food')

    def test_aviso_repetido_nao_duplica(self, _imp, _conf):
        primeiro, criado1 = p99.receber_pedido_novo(self.store, _pedido_novo())
        segundo, criado2 = p99.receber_pedido_novo(self.store, _pedido_novo())
        self.assertTrue(criado1)
        self.assertFalse(criado2)
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(StoreOrder.objects.filter(store=self.store).count(), 1)

    def test_imprime_e_confirma_depois_do_commit(self, imprimir, confirmar):
        with self.captureOnCommitCallbacks(execute=True):
            pedido, _ = p99.receber_pedido_novo(self.store, _pedido_novo())
        imprimir.assert_called_once_with(pedido.pk)
        confirmar.assert_called_once_with(pedido.pk)


class _RespostaFalsa:
    def __init__(self, corpo):
        self._corpo = corpo
        self.status_code = 200

    def json(self):
        return self._corpo


def _ok(dados=True):
    return _RespostaFalsa({'errno': 0, 'errmsg': 'ok', 'data': dados})


TOKEN_OK = {'auth_token': 'TOKEN-A', 'token_expiration_time': 4102444800}


class TokenTests(Base):
    @mock.patch('apps.stores.services.pedidos_da_99.requests')
    def test_busca_token_com_credenciais_e_guarda(self, req):
        req.get.return_value = _ok(TOKEN_OK)
        self.assertEqual(p99.token_da_loja(self.store), 'TOKEN-A')
        self.assertEqual(p99.token_da_loja(self.store), 'TOKEN-A')
        self.assertEqual(req.get.call_count, 1)
        url, = req.get.call_args.args
        self.assertEqual(url, 'https://openapi.99food.com/v1/auth/authtoken/get')
        self.assertEqual(req.get.call_args.kwargs['params'], {
            'app_id': '1152921557674426642', 'app_secret': 'segredo', 'app_shop_id': 'loja-99'})

    @override_settings(NINETY_NINE_APP_SECRET='')
    def test_sem_credencial_recusa_sem_chamar(self):
        with self.assertRaises(p99.ErroDa99):
            p99.token_da_loja(self.store)


@mock.patch('apps.stores.services.pedidos_da_99.requests')
class AcoesTests(Base):
    def _pedido(self):
        with mock.patch.object(p99, 'confirmar_depois'), mock.patch.object(p99, 'imprimir_depois'):
            pedido, _ = p99.receber_pedido_novo(self.store, _pedido_novo())
        return pedido

    def test_confirmar_manda_order_id_de_64_bits(self, req):
        req.get.return_value = _ok(TOKEN_OK)
        req.post.return_value = _ok(True)
        pedido = self._pedido()
        p99.confirmar(pedido)
        url = req.post.call_args.args[0]
        self.assertEqual(url, 'https://openapi.99food.com/v1/order/order/confirm')
        self.assertEqual(req.post.call_args.kwargs['json'], {'auth_token': 'TOKEN-A', 'order_id': PEDIDO})
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'confirmed')
        self.assertTrue(pedido.metadata['99food']['confirmado'])

    def test_token_vencido_renova_e_tenta_de_novo(self, req):
        req.get.side_effect = [_ok(TOKEN_OK), _ok(True), _ok(dict(TOKEN_OK, auth_token='TOKEN-B'))]
        req.post.side_effect = [_RespostaFalsa({'errno': 10102, 'errmsg': 'expired'}), _ok(True)]
        p99.confirmar(self._pedido())
        self.assertEqual(req.post.call_args.kwargs['json']['auth_token'], 'TOKEN-B')

    def test_erro_da_99_fica_registrado_no_pedido(self, req):
        req.get.return_value = _ok(TOKEN_OK)
        req.post.return_value = _RespostaFalsa({'errno': 40001, 'errmsg': 'order status error'})
        pedido = self._pedido()
        with self.assertRaises(p99.ErroDa99):
            p99.confirmar(pedido)
        pedido.refresh_from_db()
        self.assertIn('order status error', pedido.metadata['99food']['ultimo_erro'])

    def test_status_do_painel_vira_acao_na_99(self, req):
        req.get.return_value = _ok(TOKEN_OK)
        req.post.return_value = _ok(True)
        pedido = self._pedido()
        p99.avisar_status(pedido, 'ready')
        self.assertTrue(req.post.call_args.args[0].endswith('/order/order/ready'))
        p99.avisar_status(pedido, 'delivered')
        self.assertTrue(req.post.call_args.args[0].endswith('/order/order/delivered'))
        p99.avisar_status(pedido, 'cancelled', motivo='Acabou o produto')
        self.assertTrue(req.post.call_args.args[0].endswith('/order/order/cancel'))
        self.assertEqual(req.post.call_args.kwargs['json']['reason_id'], 1010)  # item esgotado
        self.assertEqual(req.post.call_args.kwargs['json']['reason'], 'Acabou o produto')

    def test_motivo_sem_par_na_99_vai_como_outro_com_o_texto(self, req):
        req.get.return_value = _ok(TOKEN_OK)
        req.post.return_value = _ok(True)
        p99.avisar_status(self._pedido(), 'cancelled', motivo='Cliente ligou desistindo')
        self.assertEqual(req.post.call_args.kwargs['json']['reason_id'], 1080)
        self.assertEqual(req.post.call_args.kwargs['json']['reason'], 'Cliente ligou desistindo')

    def test_entregue_so_vai_para_a_99_quando_a_entrega_e_da_loja(self, req):
        req.get.return_value = _ok(TOKEN_OK)
        req.post.return_value = _ok(True)
        with mock.patch.object(p99, 'confirmar_depois'), mock.patch.object(p99, 'imprimir_depois'):
            pedido, _ = p99.receber_pedido_novo(self.store, _pedido_novo(delivery_type=1))
        p99.avisar_status(pedido, 'delivered')
        req.post.assert_not_called()

    def test_pedido_que_nao_e_da_99_nao_chama_nada(self, req):
        pedido = StoreOrder.objects.create(
            store=self.store, customer_name='X', customer_phone='', subtotal=1, total=1)
        p99.avisar_status(pedido, 'ready')
        req.post.assert_not_called()
        req.get.assert_not_called()


@mock.patch('apps.stores.services.pedidos_da_99.confirmar_depois')
@mock.patch('apps.stores.services.pedidos_da_99.imprimir_depois')
class AvisosDaquiPraLaTests(Base):
    def test_cancelado_na_99_cancela_aqui_sem_mandar_de_volta(self, _imp, _conf):
        pedido, _ = p99.receber_pedido_novo(self.store, _pedido_novo())
        with mock.patch.object(p99, 'avisar_status_depois') as volta:
            p99.aplicar_aviso(self.store, 'orderCancel', {'order_id': PEDIDO})
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'cancelled')
        self.assertEqual(pedido.cancel_reason, 'Cancelado na 99Food')
        volta.assert_not_called()

    def test_concluido_na_99_marca_entregue(self, _imp, _conf):
        pedido, _ = p99.receber_pedido_novo(self.store, _pedido_novo())
        p99.aplicar_aviso(self.store, 'orderFinish', {'order_id': PEDIDO})
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'delivered')

    def test_aviso_de_pedido_desconhecido_e_ignorado(self, _imp, _conf):
        self.assertFalse(p99.aplicar_aviso(self.store, 'orderCancel', {'order_id': 1}))


@mock.patch('apps.stores.services.pedidos_da_99.confirmar_depois')
@mock.patch('apps.stores.services.pedidos_da_99.imprimir_depois')
class NumeroDoPedidoTests(Base):
    """O "#16" que o app da 99 e o entregador falam. Sem ele a loja não acha o
    pedido no quadro quando o entregador chega (05/11: o #16 não apareceu)."""

    def _numero(self, **mudancas):
        pedido, _ = p99.receber_pedido_novo(self.store, _pedido_novo(**mudancas))
        pedido.refresh_from_db()
        return pedido.metadata['99food']['numero']

    def test_numero_em_texto_vira_inteiro(self, _imp, _conf):
        self.assertEqual(self._numero(order_index='16'), 16)

    def test_numero_fora_do_order_info(self, _imp, _conf):
        dados = _pedido_novo(order_index=None)
        dados['order_index'] = 16
        pedido, _ = p99.receber_pedido_novo(self.store, dados)
        self.assertEqual(pedido.metadata['99food']['numero'], 16)

    def test_numero_com_outro_nome_de_campo(self, _imp, _conf):
        dados = _pedido_novo()
        del dados['order_info']['order_index']
        dados['order_info']['orderIndex'] = 16
        pedido, _ = p99.receber_pedido_novo(self.store, dados)
        self.assertEqual(pedido.metadata['99food']['numero'], 16)

    def test_sem_numero_fica_vazio_e_nao_quebra(self, _imp, _conf):
        dados = _pedido_novo()
        del dados['order_info']['order_index']
        pedido, _ = p99.receber_pedido_novo(self.store, dados)
        self.assertIsNone(pedido.metadata['99food']['numero'])

    def test_guarda_codigos_e_quem_entrega(self, _imp, _conf):
        pedido, _ = p99.receber_pedido_novo(
            self.store, _pedido_novo(takeaway_code='4321', delivery_type=1))
        dados = pedido.metadata['99food']
        self.assertEqual(dados['codigo_entrega'], '5000')
        self.assertEqual(dados['codigo_retirada'], '4321')
        self.assertEqual(dados['quem_entrega'], 'entregador da 99')
