"""Pedido do iFood entrando no Cardapidex e o painel mandando o status de volta.

Contrato da Merchant API do iFood (módulo Order v1.0):

- não há webhook obrigatório: a loja faz POLLING em
  GET /order/v1.0/events:polling a cada 30 s (é isso que mantém a loja
  "aberta" no app do iFood) e precisa dar ACK em
  POST /order/v1.0/events/acknowledgment em todo evento que recebeu, senão ele
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
            ('GET', '/order/v1.0/events:polling'): eventos,
            ('GET', f'/order/v1.0/orders/{PEDIDO}'): _pedido(),
        }
        with self._api(respostas), mock.patch.object(pif, 'imprimir_depois'), \
                mock.patch.object(pif, 'confirmar_depois'):
            resultado = pif.processar_eventos_da_loja(self.store)

        self.assertEqual(resultado['pedidos_novos'], 1)
        self.assertTrue(StoreOrder.objects.filter(source='ifood').exists())
        ack = [c for c in self.chamadas if c[1] == '/order/v1.0/events/acknowledgment']
        self.assertEqual(len(ack), 1)
        self.assertEqual(sorted(e['id'] for e in ack[0][2]), ['ev1', 'ev2'])
        polling = self.chamadas[0]
        self.assertEqual(polling[3], {'x-polling-merchants': 'merchant-1'})

    def test_evento_que_falhou_nao_recebe_ack_para_voltar_no_proximo_polling(self):
        eventos = [{'id': 'ev1', 'code': 'PLC', 'orderId': PEDIDO}]
        respostas = {
            ('GET', '/order/v1.0/events:polling'): eventos,
            ('GET', f'/order/v1.0/orders/{PEDIDO}'): pif.ErroDoIfood('503'),
        }
        with self._api(respostas):
            pif.processar_eventos_da_loja(self.store)
        self.assertFalse([c for c in self.chamadas if c[1] == '/order/v1.0/events/acknowledgment'])

    def test_sem_eventos_nao_chama_ack(self):
        with self._api({('GET', '/order/v1.0/events:polling'): None}):
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
        pedido = self._pedido_salvo()
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
        with mock.patch.object(pif, 'processar_eventos_da_loja') as processar:
            buscar_pedidos_do_ifood()
        processar.assert_not_called()

    def test_tarefa_passa_so_pelas_lojas_conectadas(self):
        from apps.stores.tasks import buscar_pedidos_do_ifood
        dono = User.objects.create_user(username='dono-polling', password='x')
        ligada = Store.objects.create(billing_exempt=True, name='A', slug='a-ifood', owner=dono,
                                      store_type='food', status='active')
        desligada = Store.objects.create(billing_exempt=True, name='B', slug='b-ifood', owner=dono,
                                         store_type='food', status='active')
        StoreIfoodIntegration.objects.create(store=ligada, conectado=True, refresh_token='r')
        StoreIfoodIntegration.objects.create(store=desligada, conectado=False)
        with mock.patch.object(pif, 'processar_eventos_da_loja', return_value={'eventos': 0}) as processar:
            buscar_pedidos_do_ifood()
        self.assertEqual([c.args[0].pk for c in processar.call_args_list], [ligada.pk])

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

    def test_iniciar_devolve_codigo_e_endereco_do_portal(self):
        with mock.patch('apps.stores.services.ifood_oauth._post', return_value={
            'userCode': 'ABCD-1234', 'authorizationCodeVerifier': 'v',
            'verificationUrlComplete': 'https://portal.ifood.com.br/apps/code?c=ABCD-1234',
            'verificationUrl': 'https://portal.ifood.com.br/apps/code', 'expiresIn': 600,
        }):
            r = self.client.post(f'/api/v1/stores/integracoes/ifood/iniciar/?store={self.store.slug}')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['user_code'], 'ABCD-1234')
        self.assertIn('portal.ifood.com.br', r.json()['url'])

    def test_concluir_guarda_tokens_e_descobre_a_loja_no_ifood(self):
        integ = StoreIfoodIntegration.objects.create(store=self.store, authorization_code_verifier='v')
        with mock.patch('apps.stores.services.ifood_oauth._post', return_value={
            'accessToken': 'acc', 'refreshToken': 'ref', 'expiresIn': 21600,
        }), mock.patch.object(pif, '_chamar', return_value=[{'id': 'm-9', 'name': 'Loja V Palmas'}]):
            r = self.client.post(f'/api/v1/stores/integracoes/ifood/concluir/?store={self.store.slug}',
                                 {'authorization_code': 'XYZ'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        integ.refresh_from_db()
        self.assertTrue(integ.conectado)
        self.assertEqual(integ.merchant_id, 'm-9')
        self.assertEqual(integ.merchant_name, 'Loja V Palmas')

    def test_concluir_recusado_mostra_o_motivo(self):
        StoreIfoodIntegration.objects.create(store=self.store, authorization_code_verifier='v')
        from apps.stores.services.ifood_oauth import IfoodRecusou
        with mock.patch('apps.stores.services.ifood_oauth._post', side_effect=IfoodRecusou('401: código inválido')):
            r = self.client.post(f'/api/v1/stores/integracoes/ifood/concluir/?store={self.store.slug}',
                                 {'authorization_code': 'ERRADO'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('código inválido', r.json()['detail'])

    def test_desconectar_apaga_tokens(self):
        StoreIfoodIntegration.objects.create(store=self.store, conectado=True, access_token='a',
                                             refresh_token='r', merchant_id='m')
        r = self.client.post(f'/api/v1/stores/integracoes/ifood/desconectar/?store={self.store.slug}')
        self.assertEqual(r.status_code, 200)
        integ = StoreIfoodIntegration.objects.get(store=self.store)
        self.assertFalse(integ.conectado)
        self.assertEqual(integ.access_token, '')
        self.assertEqual(integ.refresh_token, '')

    @override_settings(IFOOD_CLIENT_ID='', IFOOD_CLIENT_SECRET='')
    def test_sem_app_configurado_responde_indisponivel(self):
        r = self.client.post(f'/api/v1/stores/integracoes/ifood/iniciar/?store={self.store.slug}')
        self.assertEqual(r.status_code, 503)

    def test_loja_de_outro_dono_nao_conecta(self):
        intruso = User.objects.create_user(username='intruso-ifood', password='x')
        c = APIClient()
        c.force_authenticate(intruso)
        r = c.post(f'/api/v1/stores/integracoes/ifood/desconectar/?store={self.store.slug}')
        self.assertEqual(r.status_code, 404)
