"""Pedir atendente larga o checkout em curso.

25/09, Cê Saladas: com o carrinho errado na tela (1× Cebola roxa), a cliente
pediu atendente. A transferência limpava só as esperas de endereço e
observação — itens, forma de entrega e notas ficavam na sessão, e o botão
"💠 PIX" da mensagem anterior continuava fechando AQUELE pedido por cima do
atendente (botão do bot passa pelo modo humano, de propósito).

Contrato: quem chama gente sai do checkout. A mensagem diz que o pedido foi
deixado de lado, e clicar num botão de pagamento antigo não cria StoreOrder.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.automation.services import get_session_manager
from apps.automation.services.unified_service import UnifiedService
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '5563981545075'


class AtendenteLargaOCheckoutTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-ce-atend', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-atend', owner=owner,
        )
        self.account = WhatsAppAccount.objects.create(name='CeAtend', phone_number_id='PHATEND', waba_id='WATEND')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        StoreProduct.objects.create(
            store=self.store, name='Cebola roxa', slug='cebola', price=2.99, is_active=True, track_stock=False,
        )
        # Checkout em curso: item confirmado, retirada escolhida, observação anotada.
        self._texto('vou querer 1 cebola roxa sem casca')
        self._clicar('pedido_confirmar')
        self._clicar('order_pickup')
        self.assertTrue(self._sessao().get_pending_order_items(), 'pré-condição: carrinho aberto')

    def _bot(self):
        self.conversation.refresh_from_db()
        return UnifiedService(self.account, self.conversation, use_llm=False)

    def _texto(self, texto):
        return self._bot().process_message(texto)

    def _clicar(self, reply_id):
        return self._bot().process_message('', interactive_reply={'id': reply_id, 'title': ''})

    def _sessao(self):
        return get_session_manager(self.profile, PHONE)

    def _checkout_limpo(self):
        sessao = self._sessao()
        self.assertEqual(sessao.get_pending_order_items(), [])
        self.assertEqual(sessao.get_customer_notes(), '')
        self.assertFalse(sessao.is_waiting_for_notes())
        self.assertFalse(sessao.is_waiting_for_address())
        self.assertEqual(sessao.pedido_digitado(), {})

    def test_pedir_atendente_por_texto_larga_o_pedido(self):
        resposta = self._texto('quero falar com um atendente')

        self.assertIn('deixei seu pedido de lado', resposta.content)
        self.assertIn('o atendente monta com você', resposta.content)
        self._checkout_limpo()

    def test_botao_atendente_larga_o_pedido(self):
        resposta = self._clicar('contact_support')

        self.assertIn('deixei seu pedido de lado', resposta.content)
        self._checkout_limpo()

    def test_suporte_tambem_e_pedir_gente(self):
        resposta = self._texto('preciso de suporte')

        self.assertIn('deixei seu pedido de lado', resposta.content)
        self._checkout_limpo()

    def test_controle_sem_atendente_o_mesmo_botao_fecha_o_pedido(self):
        """Sem este controle o teste de baixo passaria por qualquer outro motivo."""
        self._clicar('pay_pickup')

        self.assertTrue(StoreOrder.objects.filter(store=self.store).exists())

    def test_botao_de_pagamento_antigo_nao_fecha_pedido(self):
        self._texto('quero falar com um atendente')

        self._clicar('pay_pickup')

        self.assertFalse(StoreOrder.objects.filter(store=self.store).exists())

    def test_sem_checkout_a_transferencia_nao_fala_de_pedido(self):
        self._sessao().reset_session()

        resposta = self._texto('quero falar com um atendente')

        self.assertNotIn('pedido de lado', resposta.content)
        self.assertIn('atend', resposta.content.lower())
