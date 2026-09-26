"""Endereço de Palmas: sem quadra, pergunta; longe demais, confirma antes de cobrar.

25/09 (CE-2609251646): "307 norte Al 19 lote 53" foi geocodificado como Plano
Diretor SUL — 14 km, R$ 19,30 de frete — e o bot cobrou sem perguntar nada.
O 0c62340 passou a mandar a quadra explícita ao Google. Faltavam duas travas:

(a) Em Palmas a quadra localiza; alameda e lote se repetem em todas. Texto
    sem quadra + setor → o bot pergunta a quadra UMA vez e junta ao texto.
(b) Distância acima de `store.metadata['distancia_maxima_sem_confirmar_km']`
    (padrão 10) → "Ficou a 14 km — confirma esse endereço?" antes do resumo
    com os botões de pagamento.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.automation.services.fluxos_do_bot import eh_fluxo_do_bot
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.stores.services.unified_delivery_service import UnifiedDeliveryService
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
GEO_NORTE = {'lat': -10.165818, 'lng': -48.351327,
             'formatted_address': 'Q. 307 Norte Alameda 19, 53 - Arno, Palmas - TO, Brasil', 'address': {}}


def _frete(km):
    return {'success': True, 'fee': 19.30, 'distance_km': km, 'duration_minutes': 25}


class _Base(TestCase):
    CIDADE = 'Palmas'
    METADATA = {}

    def setUp(self):
        owner = User.objects.create_user(username='dona-ce-quadra', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-quadra', owner=owner,
            city=self.CIDADE, metadata=dict(self.METADATA),
        )
        self.account = WhatsAppAccount.objects.create(name='CeQuadra', phone_number_id='PHQD', waba_id='WQD')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number='5563981545075')
        produto = StoreProduct.objects.create(
            store=self.store, name='Especial Filé de Frango', slug='especial', price=39.99, is_active=True,
        )
        self.handler = InteractiveReplyHandler(self.account, self.conversation, self.profile)
        sessao = self.handler._get_session_manager()
        sessao.save_pending_order_items([{'product_id': str(produto.id), 'quantity': 1}])
        sessao.save_pending_delivery_method('delivery')
        sessao.set_waiting_for_address(True)
        # Nenhum teste aqui vai à rede: o Google é sempre simulado.
        geocode = patch('apps.stores.services.geo.geo_service.geocode', return_value=GEO_NORTE)
        self.geocode = geocode.start()
        self.addCleanup(geocode.stop)

    @staticmethod
    def _texto(resultado):
        if resultado.use_interactive:
            return (resultado.interactive_data or {}).get('body') or ''
        return resultado.response_text or ''

    @staticmethod
    def _botoes(resultado):
        return [b['id'] for b in (resultado.interactive_data or {}).get('buttons', [])]


class _EnderecoDigitado(_Base):
    def setUp(self):
        super().setUp()
        seguir = patch.object(InteractiveReplyHandler, '_process_location_and_ask_payment', autospec=True)
        self.seguir = seguir.start()
        self.addCleanup(seguir.stop)


class PedeAQuadraTest(_EnderecoDigitado):
    def test_sem_quadra_pergunta_antes_de_geocodificar(self):
        resultado = self.handler._handle_address_input('Alameda 19 lote 53')

        self.geocode.assert_not_called()
        self.assertIn('Qual a quadra? (ex.: 307 Norte, ARSE 72)', self._texto(resultado))
        self.assertTrue(self.handler._get_session_manager().is_waiting_for_address())

    def test_a_quadra_respondida_se_junta_ao_texto(self):
        self.handler._handle_address_input('Alameda 19 lote 53')
        self.handler._handle_address_input('307 norte')

        self.assertEqual(self.geocode.call_args.args[0], 'Quadra 307 Norte, Alameda 19, 53, Palmas - TO')
        self.seguir.assert_called_once()

    def test_pergunta_uma_vez_so(self):
        self.handler._handle_address_input('Alameda 19 lote 53')
        self.handler._handle_address_input('perto do colégio')

        self.geocode.assert_called_once()

    def test_com_quadra_e_setor_nao_pergunta(self):
        self.handler._handle_address_input('307 norte Al 19 lote 53')

        self.geocode.assert_called_once()


class ForaDePalmasNaoPerguntaQuadraTest(_EnderecoDigitado):
    CIDADE = 'Goiânia'

    def test_endereco_de_rua_segue_direto(self):
        self.handler._handle_address_input('Rua 4, casa 3, Setor Oeste')

        self.geocode.assert_called_once()


class ConfirmaDistanciaTest(_Base):
    def _calcular(self, km):
        with patch.object(UnifiedDeliveryService, 'calculate_delivery_fee', autospec=True, return_value=_frete(km)):
            return self.handler._process_location_and_ask_payment(
                session_manager=self.handler._get_session_manager(), geo_svc=None,
                lat=GEO_NORTE['lat'], lng=GEO_NORTE['lng'],
                formatted_address=GEO_NORTE['formatted_address'],
            )

    def test_longe_pede_confirmacao_antes_de_cobrar(self):
        resultado = self._calcular(14.0)

        self.assertIn('Ficou a 14 km — confirma esse endereço?', self._texto(resultado))
        self.assertIn('307 Norte', self._texto(resultado))
        self.assertEqual(self._botoes(resultado), ['endereco_confirmado', 'new_address'])

    def test_confirmar_mostra_o_resumo_com_pagamento(self):
        self._calcular(14.0)

        resultado = self.handler.handle({'reply_id': 'endereco_confirmado', 'reply_title': '', 'original_message': ''})

        self.assertIn('Resumo do seu pedido', self._texto(resultado))
        self.assertIn('R$ 19,30', self._texto(resultado))
        self.assertIn('pay_pix', self._botoes(resultado))

    def test_perto_segue_direto_para_o_resumo(self):
        resultado = self._calcular(5.2)

        self.assertIn('Resumo do seu pedido', self._texto(resultado))
        self.assertIn('pay_pix', self._botoes(resultado))

    def test_botao_de_confirmar_passa_pelo_modo_humano(self):
        self.assertTrue(eh_fluxo_do_bot('endereco_confirmado'))


class LimiteDaLojaTest(_Base):
    METADATA = {'distancia_maxima_sem_confirmar_km': 20}

    def test_limite_configurado_na_loja(self):
        with patch.object(UnifiedDeliveryService, 'calculate_delivery_fee', autospec=True, return_value=_frete(14.0)):
            resultado = self.handler._process_location_and_ask_payment(
                session_manager=self.handler._get_session_manager(), geo_svc=None,
                lat=1.0, lng=1.0, formatted_address='Q. 307 Norte',
            )

        self.assertIn('pay_pix', self._botoes(resultado))
