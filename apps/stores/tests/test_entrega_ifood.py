"""iFood Entrega: o Cardapidex chama o entregador do iFood para pedido NOSSO.

Dono, 19/11: "chamar entregador automático pelo Cardapidex, então vamos tirar
a Uber e usar o iFood, já com preços baseados" — "10 km é o que atendemos em
média mesmo".

O fluxo (Shipping API, pedidos de fora do iFood, salesChannel POS):

    cotar      GET  /shipping/v1.0/merchants/{m}/deliveryAvailabilities?latitude&longitude
               → quoteId, quote.netValue (o que o iFood cobra da loja), distância.
    chamar     POST /shipping/v1.0/merchants/{m}/orders  → 202 {id, trackingUrl}
               O entregador é alocado depois, e o resultado chega por EVENTO.
    eventos    polling /events/v1.0/events:polling (30 s), ACK de tudo.
    cancelar   GET cancellationReasons (204 = não dá mais) → POST cancel.

Fora do raio do iFood (~10 km, DeliveryDistanceTooHigh) ou com o iFood fora,
o frete volta para a tabela da loja: o iFood é uma opção, nunca uma trava.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreOrder, StoreOrderItem
from apps.stores.models.ifood import StoreIfoodIntegration
from apps.stores.services import entrega_ifood as ent
from apps.stores.services.ifood_oauth import IfoodRecusou

User = get_user_model()

CREDENCIAIS = {'IFOOD_ENTREGAS_CLIENT_ID': 'app-e', 'IFOOD_ENTREGAS_CLIENT_SECRET': 's'}
MERCHANT = '00f0d5a7-6142-4120-b34d-1b1d36cdecec'
PINO = (-10.2102562, -48.335673)
COTACAO = {
    'id': 'quote-1', 'expirationAt': '2099-01-01T00:00:00Z', 'distance': 4200,
    'preparationTime': 0, 'hasPaymentMethods': True,
    'quote': {'grossValue': 9.9, 'discount': 0, 'raise': 0, 'netValue': 9.9},
    'deliveryTime': {'min': 1200, 'max': 1800},
}


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.dono = User.objects.create_user(username='dono-entrega-ifood', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-entrega-ifood', owner=self.dono,
            store_type='food', status='active', zip_code='77001000',
        )
        self.integ = StoreIfoodIntegration.objects.create(
            store=self.store, merchant_id=MERCHANT, conectado=True,
        )

    def _pedido(self, **campos):
        dados = dict(
            store=self.store, order_number='CE-2611190001', customer_name='Emmanuel Souza',
            customer_phone='5563999887766', subtotal=Decimal('40.00'), delivery_fee=Decimal('8.00'),
            total=Decimal('48.00'), delivery_method='delivery', payment_method='pix',
            payment_status='paid', status='confirmed',
            delivery_address={
                'street': 'Acsu So 40, Conjunto 2', 'number': '2', 'neighborhood': 'Plano Diretor Sul',
                'city': 'Palmas', 'state': 'TO', 'zip_code': '77015-558', 'complement': 'casa',
                'reference': 'portão azul', 'lat': PINO[0], 'lng': PINO[1],
            },
        )
        dados.update(campos)
        pedido = StoreOrder.objects.create(**dados)
        StoreOrderItem.objects.create(order=pedido, product_name='Salada Caesar', quantity=2,
                                      unit_price=Decimal('20.00'), subtotal=Decimal('40.00'), sku='SAL-1')
        return pedido


@override_settings(**CREDENCIAIS)
class CotacaoTest(Base):
    def test_cota_pelo_pino_e_devolve_o_valor_do_ifood(self):
        with mock.patch.object(ent.ifood_oauth, 'api', return_value=COTACAO) as api:
            c = ent.cotar(self.store, *PINO)
        self.assertEqual(c['valor'], Decimal('9.90'))
        self.assertEqual(c['quote_id'], 'quote-1')
        self.assertAlmostEqual(c['distancia_km'], 4.2)
        args, kwargs = api.call_args
        self.assertEqual(args[0], 'entregas')
        self.assertEqual(args[2], f'/shipping/v1.0/merchants/{MERCHANT}/deliveryAvailabilities')
        self.assertEqual(kwargs['params'], {'latitude': PINO[0], 'longitude': PINO[1]})

    def test_mesma_cotacao_nao_bate_no_ifood_duas_vezes(self):
        with mock.patch.object(ent.ifood_oauth, 'api', return_value=COTACAO) as api:
            ent.cotar(self.store, *PINO)
            ent.cotar(self.store, *PINO)
        self.assertEqual(api.call_count, 1)

    def test_recusa_do_ifood_vem_com_o_codigo(self):
        erro = IfoodRecusou('400', 400, '{"code": "DeliveryDistanceTooHigh", "message": "longe"}')
        with mock.patch.object(ent.ifood_oauth, 'api', side_effect=erro):
            with self.assertRaises(ent.EntregaIfoodRecusada) as ctx:
                ent.cotar(self.store, *PINO)
        self.assertEqual(ctx.exception.codigo, 'DeliveryDistanceTooHigh')

    def test_frete_do_cliente_e_cotacao_mais_acrescimo(self):
        self.integ.frete_pelo_ifood = True
        self.integ.acrescimo_frete = Decimal('1.10')
        self.integ.save()
        with mock.patch.object(ent.ifood_oauth, 'api', return_value=COTACAO):
            taxa = ent.frete_para_o_cliente(self.store, *PINO)
        self.assertEqual(taxa['fee'], Decimal('11.00'))
        self.assertEqual(taxa['quote_id'], 'quote-1')
        self.assertEqual(taxa['provider'], 'ifood')

    def test_frete_desligado_nao_cota(self):
        with mock.patch.object(ent.ifood_oauth, 'api') as api:
            self.assertIsNone(ent.frete_para_o_cliente(self.store, *PINO))
        api.assert_not_called()

    def test_fora_do_raio_do_ifood_volta_para_a_tabela(self):
        self.integ.frete_pelo_ifood = True
        self.integ.save()
        erro = IfoodRecusou('400', 400, '{"code": "DeliveryDistanceTooHigh"}')
        with mock.patch.object(ent.ifood_oauth, 'api', side_effect=erro):
            self.assertIsNone(ent.frete_para_o_cliente(self.store, *PINO))

    def test_loja_nao_aprovada_nao_usa_ifood(self):
        self.integ.conectado = False
        self.integ.frete_pelo_ifood = True
        self.integ.save()
        self.assertIsNone(ent.integracao_ativa(self.store))

    @override_settings(IFOOD_ENTREGAS_CLIENT_ID='')
    def test_app_sem_credencial_nao_usa_ifood(self):
        self.assertIsNone(ent.integracao_ativa(self.store))


@override_settings(**CREDENCIAIS)
class FreteNoCheckoutTest(Base):
    """O checkout e o mapa passam por UnifiedDeliveryService: o iFood entra ali."""

    def test_com_pino_e_frete_pelo_ifood_a_taxa_e_a_do_ifood(self):
        from apps.stores.services.unified_delivery_service import UnifiedDeliveryService
        self.integ.frete_pelo_ifood = True
        self.integ.save()
        with mock.patch.object(ent.ifood_oauth, 'api', return_value=COTACAO), \
             mock.patch.object(UnifiedDeliveryService, '_calculate_distance_and_duration',
                               return_value={'success': True, 'distance_km': 4.4, 'duration_minutes': 12}), \
             mock.patch('apps.stores.services.geo.service.GeoService.reverse_geocode', return_value={}):
            r = UnifiedDeliveryService.calculate_delivery_fee(
                store=self.store, delivery_method='delivery', lat=PINO[0], lng=PINO[1])
        self.assertTrue(r['success'])
        self.assertEqual(r['fee'], 9.9)
        self.assertEqual(r['provider'], 'ifood')
        self.assertEqual(r['ifood_quote_id'], 'quote-1')

    def test_ifood_fora_do_ar_usa_a_tabela_da_loja(self):
        from apps.stores.services.unified_delivery_service import UnifiedDeliveryService
        self.integ.frete_pelo_ifood = True
        self.integ.save()
        with mock.patch.object(ent.ifood_oauth, 'api', side_effect=IfoodRecusou('iFood fora do ar')), \
             mock.patch.object(UnifiedDeliveryService, '_calculate_distance_and_duration',
                               return_value={'success': True, 'distance_km': 4.4, 'duration_minutes': 12}), \
             mock.patch.object(UnifiedDeliveryService, '_calculate_dynamic_fee', return_value=Decimal('7.00')), \
             mock.patch('apps.stores.services.geo.service.GeoService.reverse_geocode', return_value={}):
            r = UnifiedDeliveryService.calculate_delivery_fee(
                store=self.store, delivery_method='delivery', lat=PINO[0], lng=PINO[1])
        self.assertTrue(r['success'])
        self.assertEqual(r['fee'], 7.0)
        self.assertNotEqual(r.get('provider'), 'ifood')


@override_settings(**CREDENCIAIS)
class ChamarEntregadorTest(Base):
    def _chamar(self, pedido, resposta=None):
        respostas = {
            'GET': COTACAO,
            'POST': resposta or {'id': 'entrega-1', 'trackingUrl': 'https://meupedido.ifood.com.br/x'},
        }
        chamadas = []

        def falso(app, metodo, caminho, corpo=None, **kw):
            chamadas.append((metodo, caminho, corpo, kw))
            return respostas[metodo]
        with mock.patch.object(ent.ifood_oauth, 'api', side_effect=falso):
            ent.chamar(pedido)
        return chamadas

    def test_pedido_pago_online_vai_sem_pagamento_e_com_o_cliente(self):
        pedido = self._pedido()
        chamadas = self._chamar(pedido)
        metodo, caminho, corpo, _ = chamadas[-1]
        self.assertEqual((metodo, caminho), ('POST', f'/shipping/v1.0/merchants/{MERCHANT}/orders'))
        self.assertNotIn('payments', corpo)
        self.assertEqual(corpo['customer']['name'], 'Emmanuel Souza')
        self.assertEqual(corpo['customer']['phone'],
                         {'type': 'CUSTOMER', 'countryCode': '55', 'areaCode': '63', 'number': '999887766'})
        endereco = corpo['delivery']['deliveryAddress']
        self.assertEqual(endereco['postalCode'], '77015558')
        self.assertEqual(endereco['coordinates'], {'latitude': PINO[0], 'longitude': PINO[1]})
        self.assertEqual(corpo['delivery']['quoteId'], 'quote-1')
        self.assertEqual(corpo['delivery']['merchantFee'], 8.0)
        self.assertEqual(corpo['items'][0]['name'], 'Salada Caesar')
        self.assertEqual(corpo['items'][0]['totalPrice'], 40.0)
        self.assertEqual(corpo['displayId'], '0001')

    def test_guarda_a_entrega_no_pedido(self):
        pedido = self._pedido()
        self._chamar(pedido)
        pedido.refresh_from_db()
        self.assertEqual(pedido.external_delivery_provider, 'ifood')
        self.assertEqual(pedido.external_delivery_id, 'entrega-1')
        self.assertEqual(pedido.external_delivery_url, 'https://meupedido.ifood.com.br/x')
        self.assertEqual(pedido.external_delivery_status, 'REQUESTED')
        self.assertEqual(pedido.metadata['entrega_ifood']['valor'], '9.90')

    def test_dinheiro_na_entrega_vai_como_pagamento_offline_com_troco(self):
        pedido = self._pedido(payment_method='cash', payment_status='pending', change_for=Decimal('100.00'))
        corpo = self._chamar(pedido)[-1][2]
        self.assertEqual(corpo['payments']['methods'], [
            {'method': 'CASH', 'type': 'OFFLINE', 'value': 48.0, 'cash': {'changeFor': 100.0}},
        ])

    def test_cartao_na_entrega_vai_como_credito_offline(self):
        pedido = self._pedido(payment_method='card_on_delivery', payment_status='pending')
        corpo = self._chamar(pedido)[-1][2]
        self.assertEqual(corpo['payments']['methods'][0]['method'], 'CREDIT')
        self.assertEqual(corpo['payments']['methods'][0]['type'], 'OFFLINE')

    def test_ja_chamado_nao_chama_de_novo(self):
        pedido = self._pedido(external_delivery_provider='ifood', external_delivery_id='entrega-1',
                              external_delivery_status='REQUESTED')
        with mock.patch.object(ent.ifood_oauth, 'api') as api:
            ent.chamar(pedido)
        api.assert_not_called()

    def test_falha_anterior_permite_chamar_de_novo(self):
        pedido = self._pedido(external_delivery_provider='ifood', external_delivery_id='entrega-0',
                              external_delivery_status='REQUEST_DRIVER_FAILED')
        self._chamar(pedido)
        pedido.refresh_from_db()
        self.assertEqual(pedido.external_delivery_id, 'entrega-1')

    def test_retirada_nao_chama(self):
        pedido = self._pedido(delivery_method='pickup')
        with self.assertRaises(ent.EntregaIfoodRecusada):
            ent.chamar(pedido)

    def test_recusa_fica_registrada_no_pedido(self):
        pedido = self._pedido()
        erro = IfoodRecusou('400', 400, '{"code": "OffOpeningHours", "message": "fechado"}')
        with mock.patch.object(ent.ifood_oauth, 'api', side_effect=erro):
            with self.assertRaises(ent.EntregaIfoodRecusada):
                ent.chamar(pedido)
        pedido.refresh_from_db()
        self.assertIn('fora do horário', pedido.metadata['entrega_ifood']['erro'])


@override_settings(**CREDENCIAIS)
class EventosTest(Base):
    def _evento(self, codigo, **extra):
        return {'id': f'ev-{codigo}', 'code': codigo[:3], 'fullCode': codigo, 'orderId': 'entrega-1',
                'merchantId': MERCHANT, **extra}

    def _pedido_chamado(self, **campos):
        return self._pedido(external_delivery_provider='ifood', external_delivery_id='entrega-1',
                            external_delivery_status='REQUESTED', **campos)

    def test_entregador_alocado_atualiza_o_status_da_entrega(self):
        pedido = self._pedido_chamado()
        self.assertTrue(ent.aplicar_evento(self._evento('REQUEST_DRIVER_SUCCESS')))
        pedido.refresh_from_db()
        self.assertEqual(pedido.external_delivery_status, 'REQUEST_DRIVER_SUCCESS')

    def test_codigo_de_entrega_fica_no_pedido(self):
        pedido = self._pedido_chamado()
        ent.aplicar_evento(self._evento('DELIVERY_DROP_CODE_REQUESTED', metadata={'CODE': '7766'}))
        pedido.refresh_from_db()
        self.assertEqual(pedido.external_delivery_code, '7766')

    def test_saiu_para_entrega_move_o_pedido(self):
        pedido = self._pedido_chamado(status='ready')
        with mock.patch('apps.stores.services.order_service.OrderService.update_status') as mudar:
            ent.aplicar_evento(self._evento('DELIVERY_IN_TRANSIT'))
        self.assertEqual(mudar.call_args.args[1], 'out_for_delivery')

    def test_entrega_concluida_entrega_o_pedido(self):
        self._pedido_chamado(status='out_for_delivery')
        with mock.patch('apps.stores.services.order_service.OrderService.update_status') as mudar:
            ent.aplicar_evento(self._evento('DELIVERY_CONCLUDED'))
        self.assertEqual(mudar.call_args.args[1], 'delivered')

    def test_pedido_ja_entregue_nao_volta(self):
        self._pedido_chamado(status='delivered')
        with mock.patch('apps.stores.services.order_service.OrderService.update_status') as mudar:
            ent.aplicar_evento(self._evento('DELIVERY_IN_TRANSIT'))
        mudar.assert_not_called()

    def test_evento_de_pedido_desconhecido_e_ignorado_mas_reconhecido(self):
        self.assertFalse(ent.aplicar_evento(self._evento('DELIVERY_CONCLUDED', orderId='outro')))

    def test_polling_da_ack_em_tudo(self):
        self._pedido_chamado()
        eventos = [self._evento('REQUEST_DRIVER_SUCCESS'), self._evento('DELIVERY_IN_TRANSIT', orderId='x')]
        chamadas = []

        def falso(app, metodo, caminho, corpo=None, **kw):
            chamadas.append((app, metodo, caminho, corpo, kw))
            return eventos if metodo == 'GET' else None
        with mock.patch.object(ent.ifood_oauth, 'api', side_effect=falso):
            ent.processar_eventos()
        get = chamadas[0]
        self.assertEqual((get[0], get[2]), ('entregas', '/events/v1.0/events:polling'))
        self.assertEqual(get[4]['cabecalhos'], {'x-polling-merchants': MERCHANT})
        # Sem isso o polling de logística ABRE a loja no app do iFood.
        self.assertEqual(get[4]['params'], {'excludeHeartbeat': 'true'})
        ack = chamadas[-1]
        self.assertEqual(ack[2], '/events/v1.0/events/acknowledgment')
        self.assertEqual(ack[3], [{'id': 'ev-REQUEST_DRIVER_SUCCESS'}, {'id': 'ev-DELIVERY_IN_TRANSIT'}])

    def test_evento_repetido_nao_e_aplicado_duas_vezes_mas_recebe_ack(self):
        self._pedido_chamado()
        eventos = [self._evento('REQUEST_DRIVER_SUCCESS')]
        acks = []

        def falso(app, metodo, caminho, corpo=None, **kw):
            if metodo == 'POST':
                acks.append(corpo)
            return eventos if metodo == 'GET' else None
        with mock.patch.object(ent.ifood_oauth, 'api', side_effect=falso), \
             mock.patch.object(ent, 'aplicar_evento', wraps=ent.aplicar_evento) as aplicar:
            ent.processar_eventos()
            ent.processar_eventos()  # ACK perdido: o iFood manda de novo
        self.assertEqual(aplicar.call_count, 1)
        self.assertEqual(len(acks), 2)

    def test_cliente_pede_mudanca_de_endereco(self):
        pedido = self._pedido_chamado()
        ent.aplicar_evento(self._evento('DELIVERY_ADDRESS_CHANGE_REQUESTED', metadata={
            'address': {'streetName': 'Rua Nova', 'streetNumber': '10', 'neighborhood': 'Centro',
                        'city': 'Palmas', 'state': 'TO', 'complement': 'Ap 2',
                        'coordinates': {'latitude': -10.18, 'longitude': -48.33}},
            'timeoutAt': '2099-01-01T00:00:00Z'}))
        pedido.refresh_from_db()
        mudanca = pedido.metadata['entrega_ifood']['mudanca_endereco']
        self.assertEqual(mudanca['status'], 'PEDIDA')
        self.assertIn('Rua Nova, 10', mudanca['texto'])
        self.assertEqual(mudanca['prazo'], '2099-01-01T00:00:00Z')
        self.assertTrue(ent.estado(pedido)['mudanca_endereco'])

    def test_aceitar_mudanca_troca_o_endereco_do_pedido(self):
        pedido = self._pedido_chamado()
        ent._gravar_meta(pedido, mudanca_endereco={'status': 'PEDIDA', 'endereco': {
            'street': 'Rua Nova', 'number': '10', 'neighborhood': 'Centro', 'city': 'Palmas', 'state': 'TO'}})
        with mock.patch.object(ent.ifood_oauth, 'api', return_value=None) as api:
            ent.responder_endereco(pedido, aceitar=True)
        self.assertEqual(api.call_args.args[1:3], ('POST', '/shipping/v1.0/orders/entrega-1/acceptDeliveryAddressChange'))
        pedido.refresh_from_db()
        self.assertEqual(pedido.delivery_address['street'], 'Rua Nova')
        self.assertEqual(pedido.metadata['entrega_ifood']['mudanca_endereco']['status'], 'ACEITA')

    def test_recusar_mudanca(self):
        pedido = self._pedido_chamado()
        ent._gravar_meta(pedido, mudanca_endereco={'status': 'PEDIDA', 'endereco': {}})
        with mock.patch.object(ent.ifood_oauth, 'api', return_value=None) as api:
            ent.responder_endereco(pedido, aceitar=False)
        self.assertTrue(api.call_args.args[2].endswith('/denyDeliveryAddressChange'))
        with self.assertRaises(ent.EntregaIfoodRecusada):  # já respondida
            ent.responder_endereco(pedido, aceitar=True)

    def test_sem_loja_ativa_nao_faz_polling(self):
        self.integ.conectado = False
        self.integ.save()
        with mock.patch.object(ent.ifood_oauth, 'api') as api:
            ent.processar_eventos()
        api.assert_not_called()


@override_settings(**CREDENCIAIS)
class CancelarTest(Base):
    def test_cancela_com_o_primeiro_motivo_valido(self):
        pedido = self._pedido(external_delivery_provider='ifood', external_delivery_id='entrega-1',
                              external_delivery_status='REQUEST_DRIVER_SUCCESS')
        chamadas = []

        def falso(app, metodo, caminho, corpo=None, **kw):
            chamadas.append((metodo, caminho, corpo))
            if metodo == 'GET':
                return [{'cancelCodeId': '817', 'description': 'Pedido cancelado pelo cliente'}]
            return None
        with mock.patch.object(ent.ifood_oauth, 'api', side_effect=falso):
            ent.cancelar(pedido, 'cliente desistiu')
        self.assertEqual(chamadas[0][1], '/shipping/v1.0/orders/entrega-1/cancellationReasons')
        self.assertEqual(chamadas[1][1], '/shipping/v1.0/orders/entrega-1/cancel')
        self.assertEqual(chamadas[1][2]['cancellationCode'], 817)
        pedido.refresh_from_db()
        self.assertEqual(pedido.external_delivery_status, 'CANCELLATION_REQUESTED')

    def test_cancela_com_o_motivo_escolhido_pelo_lojista(self):
        pedido = self._pedido(external_delivery_provider='ifood', external_delivery_id='entrega-1',
                              external_delivery_status='REQUEST_DRIVER_SUCCESS')
        motivos = [{'cancelCodeId': '817', 'description': 'Cliente desistiu'},
                   {'cancelCodeId': '818', 'description': 'Loja sem entregador'}]
        corpos = []

        def falso(app, metodo, caminho, corpo=None, **kw):
            corpos.append(corpo)
            return motivos if metodo == 'GET' else None
        with mock.patch.object(ent.ifood_oauth, 'api', side_effect=falso):
            self.assertEqual(ent.motivos_de_cancelamento(pedido),
                             [{'codigo': '817', 'descricao': 'Cliente desistiu'},
                              {'codigo': '818', 'descricao': 'Loja sem entregador'}])
            ent.cancelar(pedido, codigo='818')
            with self.assertRaises(ent.EntregaIfoodRecusada):
                ent.cancelar(pedido, codigo='999')
        self.assertEqual(corpos[2]['cancellationCode'], 818)
        self.assertEqual(corpos[2]['reason'], 'Loja sem entregador')

    def test_sem_motivo_disponivel_nao_da_mais_para_cancelar(self):
        pedido = self._pedido(external_delivery_provider='ifood', external_delivery_id='entrega-1',
                              external_delivery_status='DELIVERY_IN_TRANSIT')
        with mock.patch.object(ent.ifood_oauth, 'api', return_value=None):
            with self.assertRaises(ent.EntregaIfoodRecusada):
                ent.cancelar(pedido)


@override_settings(**CREDENCIAIS)
class DisparoAutomaticoTest(Base):
    def test_ao_confirmar_agenda_a_chamada_com_o_tempo_de_preparo(self):
        from apps.stores.services.order_service import OrderService
        self.integ.chamar_entregador = 'confirmado'
        self.integ.save()
        pedido = self._pedido(status='pending')
        with mock.patch('apps.stores.tasks.chamar_entregador_ifood.delay') as agendar:
            with self.captureOnCommitCallbacks(execute=True):
                OrderService().update_status(pedido, 'confirmed', notify_customer=False)
        agendar.assert_called_once_with(str(pedido.id))

    def test_modo_pronto_espera_o_pedido_ficar_pronto(self):
        from apps.stores.services.order_service import OrderService
        self.integ.chamar_entregador = 'pronto'
        self.integ.save()
        pedido = self._pedido(status='pending')
        with mock.patch('apps.stores.tasks.chamar_entregador_ifood.delay') as agendar:
            with self.captureOnCommitCallbacks(execute=True):
                OrderService().update_status(pedido, 'confirmed', notify_customer=False)
            agendar.assert_not_called()
            with self.captureOnCommitCallbacks(execute=True):
                OrderService().update_status(pedido, 'ready', notify_customer=False)
        agendar.assert_called_once()

    def test_manual_nao_chama_sozinho(self):
        from apps.stores.services.order_service import OrderService
        pedido = self._pedido(status='pending')
        with mock.patch('apps.stores.tasks.chamar_entregador_ifood.delay') as agendar:
            with self.captureOnCommitCallbacks(execute=True):
                OrderService().update_status(pedido, 'confirmed', notify_customer=False)
        agendar.assert_not_called()

    def test_pedido_que_veio_do_ifood_nao_chama(self):
        from apps.stores.services.order_service import OrderService
        self.integ.chamar_entregador = 'confirmado'
        self.integ.save()
        pedido = self._pedido(status='pending', source='ifood')
        with mock.patch('apps.stores.tasks.chamar_entregador_ifood.delay') as agendar:
            with self.captureOnCommitCallbacks(execute=True):
                OrderService().update_status(pedido, 'confirmed', notify_customer=False)
        agendar.assert_not_called()


@override_settings(**CREDENCIAIS)
class PainelDoPedidoTest(Base):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.dono)

    def test_estado_mostra_o_que_o_modal_usa(self):
        pedido = self._pedido(external_delivery_provider='ifood', external_delivery_id='entrega-1',
                              external_delivery_status='DELIVERY_IN_TRANSIT', external_delivery_code='7766',
                              external_delivery_url='https://meupedido.ifood.com.br/x')
        r = self.client.get(f'/api/v1/stores/orders/{pedido.id}/entrega-ifood/')
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertTrue(d['disponivel'])
        self.assertTrue(d['chamado'])
        self.assertTrue(d['ativo'])
        self.assertEqual(d['status_texto'], 'Saiu para entrega')
        self.assertEqual(d['codigo_entrega'], '7766')
        self.assertEqual(d['rastreio_url'], 'https://meupedido.ifood.com.br/x')

    def test_motivos_e_cancelar_com_codigo(self):
        pedido = self._pedido(external_delivery_provider='ifood', external_delivery_id='entrega-1')
        with mock.patch.object(ent, 'motivos_de_cancelamento', return_value=[{'codigo': '1', 'descricao': 'X'}]):
            r = self.client.get(f'/api/v1/stores/orders/{pedido.id}/entrega-ifood/motivos-cancelamento/')
        self.assertEqual(r.json()['motivos'][0]['codigo'], '1')
        with mock.patch.object(ent, 'cancelar') as cancelar:
            self.client.post(f'/api/v1/stores/orders/{pedido.id}/entrega-ifood/cancelar/', {'codigo': '1'}, format='json')
        self.assertEqual(cancelar.call_args.kwargs['codigo'], '1')

    def test_responder_endereco(self):
        pedido = self._pedido(external_delivery_provider='ifood', external_delivery_id='entrega-1')
        url = f'/api/v1/stores/orders/{pedido.id}/entrega-ifood/endereco/'
        self.assertEqual(self.client.post(url, {'aceitar': 'sim'}, format='json').status_code, 400)
        with mock.patch.object(ent, 'responder_endereco') as resp:
            r = self.client.post(url, {'aceitar': True}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        resp.assert_called_once()

    def test_chamar_pelo_painel(self):
        pedido = self._pedido()
        with mock.patch.object(ent, 'chamar') as chamar:
            r = self.client.post(f'/api/v1/stores/orders/{pedido.id}/entrega-ifood/chamar/')
        self.assertEqual(r.status_code, 200, r.content)
        chamar.assert_called_once()

    def test_recusa_vira_400_com_o_motivo(self):
        pedido = self._pedido()
        with mock.patch.object(ent, 'chamar', side_effect=ent.EntregaIfoodRecusada('Loja fora do horário', 'X')):
            r = self.client.post(f'/api/v1/stores/orders/{pedido.id}/entrega-ifood/chamar/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('fora do horário', r.json()['detail'])

    def test_pedido_de_outra_loja_nao_aparece(self):
        pedido = self._pedido()
        intruso = User.objects.create_user(username='intruso-entrega', password='x')
        c = APIClient()
        c.force_authenticate(intruso)
        r = c.get(f'/api/v1/stores/orders/{pedido.id}/entrega-ifood/')
        self.assertEqual(r.status_code, 404)
