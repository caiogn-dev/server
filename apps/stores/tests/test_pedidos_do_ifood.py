"""Pedido do iFood entrando no Cardapidex e o painel mandando o status de volta.

Contrato da Merchant API do iFood (módulo Order v1.0):

- não há webhook obrigatório: a loja faz POLLING em
  GET /events/v1.0/events:polling a cada 30 s (é isso que mantém a loja
  "aberta" no app do iFood) e precisa dar ACK em
  POST /events/v1.0/events/acknowledgment em todo evento que recebeu, senão ele
  volta no próximo polling;
- o evento traz só o código (PLC, CFM, CAN, CON...) e o orderId; o pedido
  inteiro vem de GET /order/v1.0/orders/{id};
- valores em REAIS com casas decimais (diferente da 99, que é em centavos);
- pedido não confirmado é cancelado pelo iFood: confirmamos logo que entra;
- ações: POST /order/v1.0/orders/{id}/confirm, /startPreparation,
  /readyToPickup, /dispatch, /requestCancellation.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.stores.models.ifood import StoreIfoodIntegration
from apps.stores.services import pedidos_do_ifood as pif

User = get_user_model()
CREDENCIAIS = {'IFOOD_CLIENT_ID': 'app-123', 'IFOOD_CLIENT_SECRET': 'segredo'}
PEDIDO = 'a1b2c3d4-0000-4000-8000-000000000001'


def _pedido(**mudancas):
    dados = {
        'id': PEDIDO,
        'displayId': '8421',
        'orderType': 'DELIVERY',
        'orderTiming': 'IMMEDIATE',
        'createdAt': '2026-11-19T15:00:00.000Z',
        'merchant': {'id': 'merchant-1', 'name': 'Cê Saladas'},
        'customer': {
            'id': 'c1', 'name': 'Maria Souza',
            'phone': {'number': '0800 705 0505', 'localizer': '12345678'},
        },
        'items': [
            {
                'index': 1, 'id': 'i1', 'name': 'Salada Queridinha', 'externalCode': 'SKU-QUERIDA',
                'quantity': 2, 'unitPrice': 29.9, 'optionsPrice': 3.0, 'totalPrice': 65.8,
                'observations': 'molho à parte',
                'options': [{'name': 'Croutons', 'quantity': 1, 'unitPrice': 3.0, 'price': 3.0}],
            },
        ],
        'benefits': [
            {'value': 10.0, 'target': 'CART', 'sponsorshipValues': [
                {'name': 'IFOOD', 'value': 6.0}, {'name': 'MERCHANT', 'value': 4.0},
            ]},
        ],
        'total': {'subTotal': 65.8, 'deliveryFee': 7.0, 'benefits': 10.0,
                  'orderAmount': 62.8, 'additionalFees': 0},
        'payments': {'prepaid': 62.8, 'pending': 0, 'methods': [
            {'value': 62.8, 'currency': 'BRL', 'method': 'CREDIT', 'type': 'ONLINE'},
        ]},
        'delivery': {
            'mode': 'DEFAULT', 'deliveredBy': 'IFOOD', 'pickupCode': '4321',
            'observations': 'portão azul',
            'deliveryAddress': {
                'streetName': 'Quadra 104 Norte', 'streetNumber': '12',
                'formattedAddress': 'Quadra 104 Norte, 12', 'neighborhood': 'Plano Diretor Norte',
                'complement': 'apto 3', 'reference': 'perto da praça', 'postalCode': '77006000',
                'city': 'Palmas', 'state': 'TO',
                'coordinates': {'latitude': -10.17, 'longitude': -48.33},
            },
        },
    }
    dados.update(mudancas)
    return dados


@override_settings(**CREDENCIAIS)
class PedidosDoIfoodTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dona-ifood-pedidos', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-ifood-pedidos', owner=self.dono,
            store_type='food', status='active',
        )
        StoreIfoodIntegration.objects.create(
            store=self.store, conectado=True, merchant_id='merchant-1',
            access_token='tok', refresh_token='ref',
            token_expires_at=timezone.now() + timedelta(hours=5),
        )
        self.chamadas = []

    def _api(self, respostas):
        """Substitui a chamada HTTP crua; `respostas` mapeia (método, caminho) → corpo."""
        def falso(store, metodo, caminho, corpo=None, cabecalhos=None):
            self.chamadas.append((metodo, caminho, corpo, cabecalhos))
            chave = (metodo, caminho)
            if chave in respostas:
                valor = respostas[chave]
                if isinstance(valor, Exception):
                    raise valor
                return valor
            return None
        return mock.patch.object(pif, '_chamar', side_effect=falso)

    # ── entrada do pedido ───────────────────────────────────────────────

    def test_pedido_novo_entra_com_valores_em_reais_e_marca_do_ifood(self):
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            with self.captureOnCommitCallbacks(execute=True):
                pedido, criado = pif.receber_pedido_novo(self.store, _pedido())

        self.assertTrue(criado)
        self.assertEqual(pedido.source, 'ifood')
        self.assertEqual(pedido.subtotal, Decimal('65.80'))
        self.assertEqual(pedido.delivery_fee, Decimal('7.00'))
        self.assertEqual(pedido.discount, Decimal('10.00'))
        # Só a parte que o iFood bancou não sai da receita da loja.
        self.assertEqual(pedido.platform_discount, Decimal('6.00'))
        self.assertEqual(pedido.total, Decimal('62.80'))
        self.assertEqual(pedido.payment_status, StoreOrder.PaymentStatus.PAID)
        self.assertEqual(pedido.delivery_method, StoreOrder.DeliveryMethod.DELIVERY)
        self.assertEqual(pedido.delivery_address['street'], 'Quadra 104 Norte')
        self.assertEqual(pedido.delivery_address['lat'], -10.17)
        self.assertEqual(pedido.external_delivery_provider, 'ifood')
        self.assertIn('4321', pedido.delivery_notes)
        self.assertIn('12345678', pedido.delivery_notes)
        dados = pedido.metadata['ifood']
        self.assertEqual(dados['order_id'], PEDIDO)
        self.assertEqual(dados['numero'], '8421')
        self.assertTrue(pedido.metadata['suppress_notifications'])

        item = pedido.items.get()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.subtotal, Decimal('65.80'))
        self.assertEqual(item.unit_price, Decimal('32.90'))
        self.assertIn('Croutons', item.variant_name)
        self.assertEqual(item.notes, 'molho à parte')

    def test_item_casa_com_produto_pelo_codigo_externo(self):
        produto = StoreProduct.objects.create(store=self.store, name='Queridinha', sku='SKU-QUERIDA', price=Decimal('29.90'))
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            pedido, _ = pif.receber_pedido_novo(self.store, _pedido())
        self.assertEqual(pedido.items.get().product, produto)

    def test_pedido_repetido_devolve_o_mesmo(self):
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            primeiro, _ = pif.receber_pedido_novo(self.store, _pedido())
            segundo, criado = pif.receber_pedido_novo(self.store, _pedido())
        self.assertFalse(criado)
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(StoreOrder.objects.filter(source='ifood').count(), 1)

    def test_dinheiro_na_entrega_fica_pendente_com_troco(self):
        pagamento = {'prepaid': 0, 'pending': 62.8, 'methods': [
            {'value': 62.8, 'method': 'CASH', 'type': 'OFFLINE', 'cash': {'changeFor': 100.0}},
        ]}
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            pedido, _ = pif.receber_pedido_novo(self.store, _pedido(payments=pagamento))
        self.assertEqual(pedido.payment_status, StoreOrder.PaymentStatus.PENDING)
        self.assertEqual(pedido.payment_method, 'cash')
        self.assertEqual(pedido.change_for, Decimal('100.00'))

    def test_retirada_nao_tem_endereco(self):
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            pedido, _ = pif.receber_pedido_novo(
                self.store, _pedido(orderType='TAKEOUT', delivery=None, takeout={'mode': 'DEFAULT'}),
            )
        self.assertEqual(pedido.delivery_method, StoreOrder.DeliveryMethod.PICKUP)
        self.assertEqual(pedido.delivery_address, {})
        self.assertEqual(pedido.external_delivery_provider, '')

    # ── polling + ACK ───────────────────────────────────────────────────

    def test_polling_cria_pedido_e_da_ack_em_todos_os_eventos(self):
        eventos = [
            {'id': 'ev1', 'code': 'PLC', 'fullCode': 'PLACED', 'orderId': PEDIDO, 'merchantId': 'merchant-1'},
            {'id': 'ev2', 'code': 'XYZ', 'fullCode': 'ALGO_QUE_NAO_USAMOS', 'orderId': PEDIDO},
        ]
        respostas = {
            ('GET', '/events/v1.0/events:polling'): eventos,
            ('GET', f'/order/v1.0/orders/{PEDIDO}'): _pedido(),
        }
        with self._api(respostas), mock.patch.object(pif, 'imprimir_depois'), \
                mock.patch.object(pif, 'confirmar_depois'):
            resultado = pif.processar_eventos_da_loja(self.store)

        self.assertEqual(resultado['pedidos_novos'], 1)
        self.assertTrue(StoreOrder.objects.filter(source='ifood').exists())
        ack = [c for c in self.chamadas if c[1] == '/events/v1.0/events/acknowledgment']
        self.assertEqual(len(ack), 1)
        self.assertEqual(sorted(e['id'] for e in ack[0][2]), ['ev1', 'ev2'])
        polling = self.chamadas[0]
        self.assertEqual(polling[3], {'x-polling-merchants': 'merchant-1'})

    def test_evento_repetido_pelo_id_nao_e_reaplicado(self):
        from django.core.cache import cache
        cache.clear()
        eventos = [{'id': 'ev-hsd', 'code': 'HSD', 'orderId': PEDIDO,
                    'metadata': {'id': 'd-9', 'message': 'x'}}]
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            pif.receber_pedido_novo(self.store, _pedido())
        with self._api({('GET', '/events/v1.0/events:polling'): eventos}), \
             mock.patch.object(pif, 'aplicar_evento', wraps=pif.aplicar_evento) as aplicar:
            pif.processar_eventos_da_loja(self.store)
            pif.processar_eventos_da_loja(self.store)
        self.assertEqual(aplicar.call_count, 1)
        acks = [c for c in self.chamadas if c[1] == '/events/v1.0/events/acknowledgment']
        self.assertEqual(len(acks), 2)

    def test_evento_que_falhou_nao_recebe_ack_para_voltar_no_proximo_polling(self):
        eventos = [{'id': 'ev1', 'code': 'PLC', 'orderId': PEDIDO}]
        respostas = {
            ('GET', '/events/v1.0/events:polling'): eventos,
            ('GET', f'/order/v1.0/orders/{PEDIDO}'): pif.ErroDoIfood('503'),
        }
        with self._api(respostas):
            pif.processar_eventos_da_loja(self.store)
        self.assertFalse([c for c in self.chamadas if c[1] == '/events/v1.0/events/acknowledgment'])

    def test_eventos_sao_aplicados_na_ordem_em_que_aconteceram(self):
        eventos = [
            {'id': 'b', 'code': 'CON', 'orderId': PEDIDO, 'createdAt': '2026-11-19T15:10:00.000Z'},
            {'id': 'a', 'code': 'CFM', 'orderId': PEDIDO, 'createdAt': '2026-11-19T15:01:00.000Z'},
        ]
        self._pedido_salvo()
        with self._api({('GET', '/events/v1.0/events:polling'): eventos}), \
             mock.patch.object(pif, 'aplicar_evento', return_value=True) as aplicar:
            pif.processar_eventos_da_loja(self.store)
        self.assertEqual([c.args[1]['id'] for c in aplicar.call_args_list], ['a', 'b'])

    def test_evento_que_falha_sempre_recebe_ack_depois_de_5_tentativas(self):
        from django.core.cache import cache
        cache.clear()
        eventos = [{'id': 'ev-ruim', 'code': 'PLC', 'orderId': PEDIDO}]
        respostas = {
            ('GET', '/events/v1.0/events:polling'): eventos,
            ('GET', f'/order/v1.0/orders/{PEDIDO}'): pif.ErroDoIfood('400'),
        }
        with self._api(respostas):
            for _ in range(5):
                pif.processar_eventos_da_loja(self.store)
        acks = [c for c in self.chamadas if c[1] == '/events/v1.0/events/acknowledgment']
        self.assertEqual(len(acks), 1)
        self.assertEqual(acks[0][2], [{'id': 'ev-ruim'}])

    def test_uma_chamada_de_polling_para_varias_lojas(self):
        dono = User.objects.create_user(username='dono-lote', password='x')
        outra = Store.objects.create(billing_exempt=True, name='Agrião', slug='agriao-lote', owner=dono,
                                     store_type='food', status='active')
        StoreIfoodIntegration.objects.create(store=outra, conectado=True, merchant_id='merchant-2')
        eventos = [
            {'id': 'e1', 'code': 'CON', 'orderId': 'x1', 'merchantId': 'merchant-1'},
            {'id': 'e2', 'code': 'CON', 'orderId': 'x2', 'merchantId': 'merchant-2'},
        ]
        with self._api({('GET', '/events/v1.0/events:polling'): eventos}), \
             mock.patch.object(pif, 'aplicar_evento', return_value=False) as aplicar:
            pif.processar_eventos([self.store, outra])
        polling = [c for c in self.chamadas if c[1] == '/events/v1.0/events:polling']
        self.assertEqual(len(polling), 1)
        self.assertEqual(set(polling[0][3]['x-polling-merchants'].split(',')), {'merchant-1', 'merchant-2'})
        lojas = {c.args[1]['id']: c.args[0].pk for c in aplicar.call_args_list}
        self.assertEqual(lojas, {'e1': self.store.pk, 'e2': outra.pk})
        acks = [c for c in self.chamadas if c[1] == '/events/v1.0/events/acknowledgment']
        self.assertEqual(sorted(e['id'] for e in acks[0][2]), ['e1', 'e2'])

    def test_sem_eventos_nao_chama_ack(self):
        with self._api({('GET', '/events/v1.0/events:polling'): None}):
            resultado = pif.processar_eventos_da_loja(self.store)
        self.assertEqual(resultado['eventos'], 0)
        self.assertEqual(len(self.chamadas), 1)

    def test_cancelado_no_ifood_cancela_no_painel_sem_mandar_de_volta(self):
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            pedido, _ = pif.receber_pedido_novo(self.store, _pedido())
        with self._api({}):
            pif.aplicar_evento(self.store, {'id': 'e', 'code': 'CAN', 'orderId': PEDIDO})
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, StoreOrder.OrderStatus.CANCELLED)
        self.assertTrue(pedido.metadata['ifood']['cancelado_no_ifood'])
        with self._api({}):
            pif.avisar_status(pedido, 'cancelled', 'loja fechada')
        self.assertFalse([c for c in self.chamadas if 'requestCancellation' in c[1]])

    def test_concluido_no_ifood_vira_entregue(self):
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            pedido, _ = pif.receber_pedido_novo(self.store, _pedido())
        with self._api({}):
            pif.aplicar_evento(self.store, {'id': 'e', 'code': 'CON', 'orderId': PEDIDO})
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, StoreOrder.OrderStatus.DELIVERED)

    # ── painel → iFood ─────────────────────────────────────────────────

    def _pedido_salvo(self, **mudancas):
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            pedido, _ = pif.receber_pedido_novo(self.store, _pedido(**mudancas))
        return pedido

    def test_confirmar_chama_o_ifood_uma_vez_so(self):
        pedido = self._pedido_salvo()
        with self._api({}):
            pif.confirmar(pedido)
            pif.confirmar(pedido)
        confirmacoes = [c for c in self.chamadas if c[1].endswith('/confirm')]
        self.assertEqual(len(confirmacoes), 1)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, StoreOrder.OrderStatus.CONFIRMED)

    def test_pronto_na_retirada_avisa_ready_to_pickup(self):
        pedido = self._pedido_salvo(orderType='TAKEOUT', delivery=None)
        with self._api({}):
            pif.avisar_status(pedido, 'ready')
        self.assertTrue(any(c[1].endswith('/readyToPickup') for c in self.chamadas))

    def test_saiu_para_entrega_avisa_dispatch(self):
        pedido = self._pedido_salvo(delivery=dict(_pedido()['delivery'], deliveredBy='MERCHANT'))
        with self._api({}):
            pif.avisar_status(pedido, 'out_for_delivery')
        self.assertTrue(any(c[1].endswith('/dispatch') for c in self.chamadas))

    def test_cancelar_pede_cancelamento_com_codigo_do_ifood(self):
        pedido = self._pedido_salvo()
        motivos = [{'cancelCodeId': '501', 'description': 'Problemas de sistema'},
                   {'cancelCodeId': '503', 'description': 'Item indisponível'}]
        with self._api({('GET', f'/order/v1.0/orders/{PEDIDO}/cancellationReasons'): motivos}):
            pif.avisar_status(pedido, 'cancelled', 'acabou o item')
        pedido_cancelamento = [c for c in self.chamadas if c[1].endswith('/requestCancellation')]
        self.assertEqual(len(pedido_cancelamento), 1)
        self.assertEqual(pedido_cancelamento[0][2]['cancellationCode'], '503')

    # ── critérios de homologação do Order ────────────────────────────────

    def test_entrega_propria_avisa_pronto_antes_de_despachar(self):
        pedido = self._pedido_salvo(delivery=dict(_pedido()['delivery'], deliveredBy='MERCHANT'))
        with self._api({}):
            pif.avisar_status(pedido, 'out_for_delivery')
        acoes = [c[1].rsplit('/', 1)[-1] for c in self.chamadas if c[0] == 'POST']
        self.assertLess(acoes.index('readyToPickup'), acoes.index('dispatch'))

    def test_pronto_tambem_avisa_na_entrega(self):
        pedido = self._pedido_salvo(delivery=dict(_pedido()['delivery'], deliveredBy='MERCHANT'))
        with self._api({}):
            pif.avisar_status(pedido, 'ready')
            pif.avisar_status(pedido, 'out_for_delivery')
        prontos = [c for c in self.chamadas if c[1].endswith('/readyToPickup')]
        self.assertEqual(len(prontos), 1)  # não repete no despacho

    def test_entregador_do_ifood_nao_recebe_dispatch_da_loja(self):
        pedido = self._pedido_salvo()  # deliveredBy IFOOD
        with self._api({}):
            pif.avisar_status(pedido, 'out_for_delivery')
        self.assertFalse(any(c[1].endswith('/dispatch') for c in self.chamadas))

    def test_comanda_mostra_bandeira_documento_e_quem_paga_o_cupom(self):
        pedido = self._pedido_salvo(
            customer=dict(_pedido()['customer'], documentNumber='12345678909'),
            payments={'prepaid': 62.8, 'pending': 0, 'methods': [
                {'value': 62.8, 'currency': 'BRL', 'method': 'CREDIT', 'type': 'ONLINE',
                 'card': {'brand': 'VISA'}}]},
        )
        notas = pedido.delivery_notes
        self.assertIn('VISA', notas)
        self.assertIn('CPF/CNPJ na nota: 12345678909', notas)
        self.assertIn('iFood R$ 6,00', notas)
        self.assertIn('loja R$ 4,00', notas)
        self.assertEqual(pedido.metadata['ifood']['documento'], '12345678909')

    def test_troco_aparece_na_comanda(self):
        pedido = self._pedido_salvo(payments={'prepaid': 0, 'pending': 62.8, 'methods': [
            {'value': 62.8, 'method': 'CASH', 'type': 'OFFLINE', 'cash': {'changeFor': 100}}]})
        self.assertIn('troco de R$ 37,20', pedido.delivery_notes)

    def test_negociacao_fica_no_pedido_para_a_loja_responder(self):
        pedido = self._pedido_salvo()
        evento = {'id': 'e-hsd', 'code': 'HSD', 'fullCode': 'HANDSHAKE_DISPUTE', 'orderId': PEDIDO,
                  'metadata': {'id': 'd-1', 'action': 'CANCELLATION', 'handshakeType': 'AFTER_DELIVERY',
                               'message': 'Comida chegou fria', 'expiresAt': '2099-01-01T00:00:00Z',
                               'timeoutAction': 'REJECT_CANCELLATION',
                               'acceptCancellationReasons': ['PRODUCT_QUALITY'],
                               'alternatives': [{'id': 'alt-1', 'type': 'REFUND',
                                                 'metadata': {'maxAmount': {'value': '5000', 'currency': 'BRL'}}}]}}
        self.assertTrue(pif.aplicar_evento(self.store, evento))
        pedido.refresh_from_db()
        disputa = pedido.metadata['ifood']['disputa']
        self.assertEqual(disputa['id'], 'd-1')
        self.assertEqual(disputa['mensagem'], 'Comida chegou fria')
        self.assertEqual(disputa['status'], 'ABERTA')

    def test_responder_negociacao(self):
        pedido = self._pedido_salvo()
        pif._registrar(pedido, disputa={'id': 'd-1', 'status': 'ABERTA', 'motivos_aceite': ['PRODUCT_QUALITY']})
        with self._api({}):
            pif.responder_disputa(pedido, 'aceitar')
        self.assertEqual(self.chamadas[-1][1], '/order/v1.0/disputes/d-1/accept')
        self.assertEqual(self.chamadas[-1][2]['reason'], 'PRODUCT_QUALITY')
        pedido.refresh_from_db()
        self.assertEqual(pedido.metadata['ifood']['disputa']['status'], 'RESPONDIDA')

    def test_recusar_e_contrapropor(self):
        pedido = self._pedido_salvo()
        pif._registrar(pedido, disputa={'id': 'd-2', 'status': 'ABERTA'})
        with self._api({}):
            pif.responder_disputa(pedido, 'recusar', motivo='INVENTORY_CHECK')
        self.assertEqual(self.chamadas[-1][1:], ('/order/v1.0/disputes/d-2/reject', {'reason': 'INVENTORY_CHECK'}, None))
        pif._registrar(pedido, disputa={'id': 'd-3', 'status': 'ABERTA'})
        with self._api({}):
            pif.responder_disputa(pedido, 'alternativa', tipo='REFUND', valor_centavos=1500)
        self.assertEqual(self.chamadas[-1][2], {'type': 'REFUND', 'metadata': {'amount': {'value': '1500', 'currency': 'BRL'}}})

    def test_resultado_da_negociacao_fecha_a_disputa(self):
        pedido = self._pedido_salvo()
        pif._registrar(pedido, disputa={'id': 'd-1', 'status': 'RESPONDIDA'})
        pif.aplicar_evento(self.store, {'id': 'e-hss', 'code': 'HSS', 'orderId': PEDIDO,
                                        'metadata': {'disputeId': 'd-1', 'status': 'EXPIRED'}})
        pedido.refresh_from_db()
        self.assertEqual(pedido.metadata['ifood']['disputa']['status'], 'EXPIRED')

    def test_cancelar_com_o_motivo_escolhido_do_ifood(self):
        pedido = self._pedido_salvo()
        motivos = [{'cancelCodeId': '501', 'description': 'Problemas de sistema'},
                   {'cancelCodeId': '503', 'description': 'Item indisponível'}]
        with self._api({('GET', f'/order/v1.0/orders/{PEDIDO}/cancellationReasons'): motivos}):
            self.assertEqual(pif.motivos_de_cancelamento(pedido),
                             [{'codigo': '501', 'descricao': 'Problemas de sistema'},
                              {'codigo': '503', 'descricao': 'Item indisponível'}])
            pif.cancelar_no_ifood(pedido, '501')
        caminhos = [c[1] for c in self.chamadas]
        # consulta os motivos ANTES de pedir o cancelamento
        self.assertLess(caminhos.index(f'/order/v1.0/orders/{PEDIDO}/cancellationReasons'),
                        caminhos.index(f'/order/v1.0/orders/{PEDIDO}/requestCancellation'))
        corpo = [c for c in self.chamadas if c[1].endswith('/requestCancellation')][0][2]
        self.assertEqual(corpo['cancellationCode'], '501')
        pedido.refresh_from_db()
        # Só o iFood cancela: o pedido espera o evento CAN.
        self.assertNotEqual(pedido.status, StoreOrder.OrderStatus.CANCELLED)
        self.assertEqual(pedido.metadata['ifood']['cancelamento']['status'], 'ENVIADO')
        self.assertEqual(pedido.metadata['ifood']['cancelamento']['codigo'], '501')
        # o aviso automático de status não pede cancelamento de novo
        self.chamadas = []
        with self._api({}):
            pif.avisar_status(pedido, 'cancelled', 'x')
        self.assertFalse(any(c[1].endswith('/requestCancellation') for c in self.chamadas))

    def test_ciclo_do_cancelamento_pedido_pela_loja(self):
        pedido = self._pedido_salvo()
        motivos = [{'cancelCodeId': '501', 'description': 'Problemas de sistema'}]
        with self._api({('GET', f'/order/v1.0/orders/{PEDIDO}/cancellationReasons'): motivos}):
            pif.cancelar_no_ifood(pedido, '501')
        with self._api({}):
            pif.aplicar_evento(self.store, {'id': 'e1', 'code': 'CAR', 'orderId': PEDIDO})
        pedido.refresh_from_db()
        self.assertEqual(pedido.metadata['ifood']['cancelamento']['status'], 'EM_ANALISE')
        self.assertNotIn('pedido_do_cliente', pedido.metadata['ifood'])
        with self._api({}):
            pif.aplicar_evento(self.store, {'id': 'e2', 'code': 'CAN', 'orderId': PEDIDO, 'metadata': {
                'CANCEL_CODE': '501', 'CANCELLATION_ORIGIN': 'RESTAURANT',
                'CANCEL_REASON': 'Problemas de sistema na loja'}})
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, StoreOrder.OrderStatus.CANCELLED)
        self.assertEqual(pedido.metadata['ifood']['cancelamento']['status'], 'CANCELADO')
        self.assertEqual(pedido.metadata['ifood']['cancelamento']['origem'], 'RESTAURANT')
        self.assertIn('Problemas de sistema na loja', pedido.cancel_reason)

    def test_cancelamento_negado_volta_o_pedido_e_avisa(self):
        pedido = self._pedido_salvo()
        motivos = [{'cancelCodeId': '501', 'description': 'Problemas de sistema'}]
        with self._api({('GET', f'/order/v1.0/orders/{PEDIDO}/cancellationReasons'): motivos}):
            pif.cancelar_no_ifood(pedido, '501')
        with self._api({}):
            pif.aplicar_evento(self.store, {'id': 'e1', 'code': 'CARF', 'orderId': PEDIDO,
                                            'metadata': {'reason': 'Pedido já saiu'}})
        pedido.refresh_from_db()
        self.assertNotEqual(pedido.status, StoreOrder.OrderStatus.CANCELLED)
        self.assertEqual(pedido.metadata['ifood']['cancelamento']['status'], 'NEGADO')
        self.assertIn('negou', pedido.metadata['ifood']['ultimo_erro'])
        # negado → a loja pode tentar de novo
        self.chamadas = []
        with self._api({('GET', f'/order/v1.0/orders/{PEDIDO}/cancellationReasons'): motivos}):
            pif.cancelar_no_ifood(pedido, '501')
        self.assertTrue(any(c[1].endswith('/requestCancellation') for c in self.chamadas))

    def test_cancelamento_ja_enviado_nao_e_enviado_de_novo(self):
        pedido = self._pedido_salvo()
        motivos = [{'cancelCodeId': '501', 'description': 'Problemas de sistema'}]
        with self._api({('GET', f'/order/v1.0/orders/{PEDIDO}/cancellationReasons'): motivos}):
            pif.cancelar_no_ifood(pedido, '501')
            with self.assertRaises(pif.ErroDoIfood):
                pif.cancelar_no_ifood(pedido, '501')
        self.assertEqual(len([c for c in self.chamadas if c[1].endswith('/requestCancellation')]), 1)

    def test_cancelado_pelo_cliente_ou_ifood_registra_a_origem(self):
        pedido = self._pedido_salvo()
        with self._api({}):
            pif.aplicar_evento(self.store, {'id': 'e', 'code': 'CAN', 'orderId': PEDIDO, 'metadata': {
                'CANCELLATION_ORIGIN': 'CONSUMER', 'CANCEL_REASON': 'Desisti'}})
        pedido.refresh_from_db()
        self.assertEqual(pedido.metadata['ifood']['cancelamento']['origem'], 'CONSUMER')
        self.assertIn('cliente', pedido.cancel_reason.lower())

    def test_falha_do_ifood_fica_registrada_no_pedido(self):
        pedido = self._pedido_salvo()
        with self._api({('POST', f'/order/v1.0/orders/{PEDIDO}/confirm'): pif.ErroDoIfood('400: já cancelado')}):
            with self.assertRaises(pif.ErroDoIfood):
                pif.confirmar(pedido)
        pedido.refresh_from_db()
        self.assertIn('já cancelado', pedido.metadata['ifood']['ultimo_erro'])

    def test_pedido_de_outro_canal_nao_vai_ao_ifood(self):
        outro = StoreOrder.objects.create(store=self.store, customer_name='X', subtotal=1, total=1)
        with self._api({}):
            pif.avisar_status(outro, 'ready')
        self.assertEqual(self.chamadas, [])

    def test_loja_sem_token_nao_chama_nada(self):
        self.store.ifood.conectado = False
        self.store.ifood.save()
        resultado = pif.processar_eventos_da_loja(self.store)
        self.assertEqual(resultado['eventos'], 0)


@override_settings(**CREDENCIAIS)
class TarefaDoPollingTest(TestCase):
    def test_beat_roda_a_cada_30_segundos(self):
        from config.celery import app
        entrada = app.conf.beat_schedule['buscar-pedidos-do-ifood']
        self.assertEqual(entrada['task'], 'apps.stores.tasks.buscar_pedidos_do_ifood')
        self.assertEqual(entrada['schedule'], 30.0)

    @override_settings(IFOOD_CLIENT_ID='', IFOOD_CLIENT_SECRET='')
    def test_sem_app_configurado_a_tarefa_nao_faz_nada(self):
        from apps.stores.tasks import buscar_pedidos_do_ifood
        with mock.patch.object(pif, 'processar_eventos') as processar:
            buscar_pedidos_do_ifood()
        processar.assert_not_called()

    def test_tarefa_passa_so_pelas_lojas_conectadas(self):
        from apps.stores.tasks import buscar_pedidos_do_ifood
        from django.core.cache import cache
        cache.clear()
        dono = User.objects.create_user(username='dono-polling', password='x')
        ligada = Store.objects.create(billing_exempt=True, name='A', slug='a-ifood', owner=dono,
                                      store_type='food', status='active')
        desligada = Store.objects.create(billing_exempt=True, name='B', slug='b-ifood', owner=dono,
                                         store_type='food', status='active')
        StoreIfoodIntegration.objects.create(store=ligada, conectado=True, merchant_id='m-a', refresh_token='r')
        StoreIfoodIntegration.objects.create(store=desligada, conectado=False, merchant_id='m-b')
        with mock.patch.object(pif, 'processar_eventos', return_value={'eventos': 0}) as processar:
            buscar_pedidos_do_ifood()
        self.assertEqual([[l.pk for l in c.args[0]] for c in processar.call_args_list], [[ligada.pk]])

    def test_duas_rodadas_ao_mesmo_tempo_nao_se_atropelam(self):
        from apps.stores.tasks import buscar_pedidos_do_ifood
        from django.core.cache import cache
        cache.clear()
        dono = User.objects.create_user(username='dono-trava', password='x')
        loja = Store.objects.create(billing_exempt=True, name='A', slug='trava-ifood', owner=dono,
                                    store_type='food', status='active')
        StoreIfoodIntegration.objects.create(store=loja, conectado=True, merchant_id='m-a')
        cache.add('ifood:polling-pedidos', 1, timeout=25)
        with mock.patch.object(pif, 'processar_eventos') as processar:
            buscar_pedidos_do_ifood()
        processar.assert_not_called()

    def test_mudar_status_no_painel_agenda_aviso_ao_ifood(self):
        from apps.stores.services.order_service import OrderService
        dono = User.objects.create_user(username='dono-status', password='x')
        loja = Store.objects.create(billing_exempt=True, name='C', slug='c-ifood', owner=dono,
                                    store_type='food', status='active')
        pedido = StoreOrder.objects.create(
            store=loja, customer_name='X', subtotal=1, total=1, source='ifood',
            metadata={'source': 'ifood', 'ifood': {'order_id': PEDIDO}},
        )
        with mock.patch.object(pif, 'avisar_status_depois') as avisar:
            with self.captureOnCommitCallbacks(execute=True):
                OrderService().update_status(pedido, 'confirmed', notify_customer=False)
        avisar.assert_called_once()
        self.assertEqual(avisar.call_args.args[1], 'confirmed')


@override_settings(**CREDENCIAIS)
class VinculoPeloPainelTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-vinculo', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Loja V', slug='loja-vinculo', owner=self.dono,
            store_type='food', status='active',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.dono)

    MERCHANT = '00f0d5a7-6142-4120-b34d-1b1d36cdecec'

    def _url(self, sufixo=''):
        return f'/api/v1/stores/integracoes/ifood/{sufixo}?store={self.store.slug}'

    def test_informar_o_id_confere_o_acesso_e_mostra_a_loja(self):
        with mock.patch('apps.stores.services.ifood_oauth.api',
                        return_value={'id': self.MERCHANT, 'name': 'Loja V Palmas'}):
            r = self.client.post(self._url(), {'merchant_id': self.MERCHANT}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['merchant_id'], self.MERCHANT)
        self.assertTrue(r.json()['conectado'])
        self.assertEqual(r.json()['loja'], 'Loja V Palmas')

    def test_id_invalido_volta_400(self):
        r = self.client.post(self._url(), {'merchant_id': '4327433'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('inválido', r.json()['detail'])

    def test_loja_sem_aprovacao_fica_aguardando_com_o_motivo(self):
        from apps.stores.services.ifood_oauth import IfoodRecusou
        with mock.patch('apps.stores.services.ifood_oauth.api', side_effect=IfoodRecusou('403: x', 403)):
            r = self.client.post(self._url(), {'merchant_id': self.MERCHANT}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['conectado'])
        self.assertIn('Portal do Parceiro', r.json()['erro'])

    def test_configura_as_entregas(self):
        StoreIfoodIntegration.objects.create(store=self.store, merchant_id=self.MERCHANT, conectado=True)
        r = self.client.post(self._url(), {
            'frete_pelo_ifood': True, 'acrescimo_frete': '1.50',
            'chamar_entregador': 'confirmado', 'tempo_preparo_min': 20,
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        integ = StoreIfoodIntegration.objects.get(store=self.store)
        self.assertTrue(integ.frete_pelo_ifood)
        self.assertEqual(str(integ.acrescimo_frete), '1.50')
        self.assertEqual(integ.chamar_entregador, 'confirmado')
        self.assertEqual(integ.tempo_preparo_min, 20)
        self.assertEqual(r.json()['acrescimo_frete'], '1.50')

    def test_opcao_invalida_de_chamar_entregador_volta_400(self):
        StoreIfoodIntegration.objects.create(store=self.store, merchant_id=self.MERCHANT)
        r = self.client.post(self._url(), {'chamar_entregador': 'sempre'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_estado_lista_tudo_que_o_painel_usa(self):
        r = self.client.get(f'/api/v1/stores/integracoes/?store={self.store.slug}')
        ifood = r.json()['ifood']
        for chave in ('disponivel', 'entregas_disponivel', 'merchant_id', 'conectado', 'loja', 'erro',
                      'frete_pelo_ifood', 'acrescimo_frete', 'chamar_entregador', 'tempo_preparo_min'):
            self.assertIn(chave, ifood)

    def test_desconectar_esquece_a_loja(self):
        StoreIfoodIntegration.objects.create(store=self.store, conectado=True, merchant_id=self.MERCHANT,
                                             frete_pelo_ifood=True)
        r = self.client.post(self._url('desconectar/'))
        self.assertEqual(r.status_code, 200)
        integ = StoreIfoodIntegration.objects.get(store=self.store)
        self.assertFalse(integ.conectado)
        self.assertEqual(integ.merchant_id, '')
        self.assertFalse(integ.frete_pelo_ifood)

    def test_loja_de_outro_dono_nao_conecta(self):
        intruso = User.objects.create_user(username='intruso-ifood', password='x')
        c = APIClient()
        c.force_authenticate(intruso)
        r = c.post(f'/api/v1/stores/integracoes/ifood/desconectar/?store={self.store.slug}')
        self.assertEqual(r.status_code, 404)


@override_settings(**CREDENCIAIS)
class PainelDoPedidoIfoodTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono-painel-ifood', password='x')
        self.store = Store.objects.create(billing_exempt=True, name='P', slug='p-ifood', owner=self.dono,
                                          store_type='food', status='active')
        StoreIfoodIntegration.objects.create(store=self.store, conectado=True, merchant_id='merchant-1')
        with mock.patch.object(pif, 'imprimir_depois'), mock.patch.object(pif, 'confirmar_depois'):
            self.pedido, _ = pif.receber_pedido_novo(self.store, _pedido())
        self.client = APIClient()
        self.client.force_authenticate(self.dono)
        self.base = f'/api/v1/stores/orders/{self.pedido.id}/ifood/'

    def test_motivos(self):
        with mock.patch.object(pif, 'motivos_de_cancelamento', return_value=[{'codigo': '501', 'descricao': 'X'}]):
            r = self.client.get(self.base + 'motivos-cancelamento/')
        self.assertEqual(r.json(), {'motivos': [{'codigo': '501', 'descricao': 'X'}]})

    def test_cancelar(self):
        with mock.patch.object(pif, 'cancelar_no_ifood') as cancelar:
            r = self.client.post(self.base + 'cancelar/', {'codigo': '501'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        cancelar.assert_called_once()

    def test_negociacao(self):
        pif._registrar(self.pedido, disputa={'id': 'd-1', 'status': 'ABERTA'})
        self.assertEqual(self.client.get(self.base + 'negociacao/').json()['disputa']['id'], 'd-1')
        with mock.patch.object(pif, 'responder_disputa', side_effect=pif.ErroDoIfood('já respondida')):
            r = self.client.post(self.base + 'negociacao/', {'resposta': 'aceitar'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_pedido_que_nao_e_do_ifood_da_404(self):
        outro = StoreOrder.objects.create(store=self.store, customer_name='X', subtotal=1, total=1)
        r = self.client.get(f'/api/v1/stores/orders/{outro.id}/ifood/negociacao/')
        self.assertEqual(r.status_code, 404)


class StatusMudadoNoIfoodTest(PedidosDoIfoodTest):
    """O lojista mexeu no Gestor de Pedidos do iFood: o painel acompanha (24/11).

    Só AVANÇA (preparo → pronto → saiu → entregue), nunca volta, e não manda
    nada de volta ao iFood — senão o eco viraria um segundo comando lá.
    """

    def _evento(self, codigo, pedido=None):
        with self._api({}), mock.patch.object(pif, 'avisar_status_depois') as volta:
            pif.aplicar_evento(self.store, {'id': f'e-{codigo}', 'code': codigo, 'orderId': PEDIDO})
        if pedido is not None:
            pedido.refresh_from_db()
        return volta

    def test_preparo_pronto_e_despachado_avancam_sem_eco(self):
        pedido = self._pedido_salvo()
        for codigo, esperado in (('PRS', 'preparing'), ('RTP', 'ready'), ('DSP', 'out_for_delivery')):
            volta = self._evento(codigo, pedido)
            self.assertEqual(pedido.status, esperado, codigo)
            volta.assert_not_called()
        self.assertFalse([c for c in self.chamadas if c[0] == 'POST'])

    def test_nao_volta_status(self):
        pedido = self._pedido_salvo()
        StoreOrder.objects.filter(pk=pedido.pk).update(status='out_for_delivery')
        self._evento('PRS', pedido)
        self.assertEqual(pedido.status, 'out_for_delivery')

    def test_cancelado_ou_entregue_nao_muda(self):
        pedido = self._pedido_salvo()
        for final in ('cancelled', 'delivered'):
            StoreOrder.objects.filter(pk=pedido.pk).update(status=final)
            self._evento('DSP', pedido)
            self.assertEqual(pedido.status, final)

    def test_despachado_na_retirada_fica_pronto(self):
        pedido = self._pedido_salvo(orderType='TAKEOUT')
        self._evento('DSP', pedido)
        self.assertEqual(pedido.status, 'ready')
