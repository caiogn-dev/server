"""Cliente que quer comprar e o bot não deixa — 07/10, Dr. Matheus (Cê Saladas).

17:56–18:26, meia hora para pedir uma salada:
- mandou a localização às 18:06; às 18:24, no botão "Entrega", o bot pediu o
  endereço de novo — o pino foi salvo com texto vazio (o Google não deu nome
  para o ponto da Orla) e "Entregar no mesmo endereço?" exige texto;
- "desisto" foi aceito como ENDEREÇO na 2ª tentativa (anti-loop) e o bot
  mostrou os botões de pagamento;
- "meia hora pra fazer um pedido" voltou o catálogo.

Quem trava no meio do pedido vai para um atendente — e o que estava sendo
montado vai junto no motivo da fila. O checkout automático sai de cena como em
toda transferência (25/09: botão de PIX antigo fechava pedido por cima do
atendente).
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.automation.services.unified_service import UnifiedService
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.intents.travou import travou_no_pedido
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '5563981007070'

TRAVOU = [
    'desisto',
    'meia hora pra fazer um pedido',
    'não consigo fazer o pedido',
    'que demora pra pedir',
    'travou aqui',
    'o bot bugou',
    'ta dificil pedir',
]
NAO_TRAVOU = [
    'quero uma queridinha sem cebola',
    'orla da graciosa',
    'Alameda 01 Quadra 03 Alc So 14, 06',
    'crédito',
    'qual prazo de entrega?',
]


@pytest.mark.parametrize('texto', TRAVOU)
def test_travou_e_reconhecido(texto):
    assert travou_no_pedido(texto), texto


@pytest.mark.parametrize('texto', NAO_TRAVOU)
def test_pedido_normal_nao_e_travou(texto):
    assert not travou_no_pedido(texto), texto


class _Loja(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-travou', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-travou', owner=owner, city='Palmas',
        )
        self.account = WhatsAppAccount.objects.create(name='CeTrav', phone_number_id='PHTRAV', waba_id='WTRAV')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        self.produto = StoreProduct.objects.create(
            store=self.store, name='Especial Filé de Frango', slug='especial', price=39.99, is_active=True,
        )
        self.handler = InteractiveReplyHandler(self.account, self.conversation, self.profile)
        self.sessao = self.handler._get_session_manager()
        self.sessao.save_pending_order_items([{'product_id': str(self.produto.id), 'quantity': 1}])

    @staticmethod
    def _texto(resultado):
        if getattr(resultado, 'use_interactive', False):
            return (resultado.interactive_data or {}).get('body') or ''
        return getattr(resultado, 'response_text', None) or getattr(resultado, 'content', '') or ''

    @staticmethod
    def _botoes(resultado):
        return [b['id'] for b in (getattr(resultado, 'interactive_data', None) or {}).get('buttons', [])]


class PinoSemNomeTest(_Loja):
    def test_pino_sem_nome_e_oferecido_de_novo_no_botao_entrega(self):
        frete = {'success': True, 'fee': 12.21, 'distance_km': 6.2, 'duration_minutes': 12}
        with patch('apps.stores.services.geo.geo_service.reverse_geocode', return_value=None), \
             patch('apps.stores.services.unified_delivery_service.UnifiedDeliveryService.calculate_delivery_fee',
                   return_value=frete):
            self.handler._handle_location_input(-10.1904064, -48.3601697)

        resultado = self.handler._handle_delivery_choice('order_delivery')

        self.assertIn('use_saved_address', self._botoes(resultado), self._texto(resultado))
        self.assertIn('Entregar no mesmo endereço', self._texto(resultado))


class TextoQueNaoEEnderecoTest(_Loja):
    def test_desisto_na_segunda_falha_nao_vira_endereco(self):
        self.sessao.save_pending_delivery_method('delivery')
        self.sessao.set_waiting_for_address(True)
        self.sessao.bump_address_attempts()  # 1ª falha já aconteceu ("orla da graciosa")
        with patch('apps.stores.services.geo.geo_service.geocode', return_value=None):
            self.handler._handle_address_input('desisto')  # 1º: sem quadra, o bot pergunta a quadra
            resultado = self.handler._handle_address_input('desisto')  # resposta: 2ª falha no mapa

        self.assertNotEqual(self.sessao.get_delivery_address_info().get('address'), 'desisto')
        self.assertNotIn('pay_pix', self._botoes(resultado))


class TravouVaiProAtendenteTest(_Loja):
    def _mensagem(self, texto):
        self.conversation.refresh_from_db()
        return UnifiedService(self.account, self.conversation, use_llm=False).process_message(texto)

    def test_meia_hora_no_meio_do_endereco_chama_atendente_com_o_pedido_no_motivo(self):
        from apps.handover.models import ConversationHandover
        self.sessao.save_pending_delivery_method('delivery')
        self.sessao.set_waiting_for_address(True)

        resposta = self._mensagem('meia hora pra fazer um pedido')

        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.mode, Conversation.ConversationMode.HUMAN)
        motivo = ConversationHandover.objects.get(conversation=self.conversation).transfer_reason
        self.assertIn('travou', motivo.lower())
        # O pedido em montagem fica no chat, para o atendente não perguntar de novo.
        self.assertIn('1x Especial Filé de Frango', resposta.content)
        self.assertNotIn('Ver catálogo', resposta.content)
