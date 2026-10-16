"""Espera de checkout esquecida não captura a conversa dias depois.

16/10, Cê Saladas (Raquel): em 14/10 o bot pediu a observação, o atendente
fechou o pedido na mão (PIX mandado pelo chat) e a espera nunca foi desligada.
Dois dias depois ela mandou "Olá" e recebeu "Ah, você quer *Cebola roxa*?
Isso é um item, não uma observação".

Contrato: a espera de observação/endereço vale 6 h a partir do último passo do
checkout — a mesma janela de "pedido recente" do bot. Passou disso, a mensagem
segue o roteamento normal.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.automation.models import CompanyProfile, CustomerSession
from apps.automation.services import get_session_manager
from apps.automation.services.fluxos_do_bot import espera_endereco
from apps.automation.services.unified_service import UnifiedService
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '5563981549999'


class EsperaDeCheckoutVenceTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-ce-vence', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-vence', owner=owner,
        )
        self.account = WhatsAppAccount.objects.create(name='CeVence', phone_number_id='PHVENCE', waba_id='WVENCE')
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
        StoreProduct.objects.create(
            store=self.store, name='Salada Caesar', slug='caesar', price=39.99, is_active=True, track_stock=False,
        )
        self._texto('vou querer 1 salada caesar')
        self._clicar('pedido_confirmar')
        self._clicar('order_pickup')
        self.assertTrue(self._sessao().is_waiting_for_notes(), 'pré-condição: bot pediu observação')

    def _bot(self):
        self.conversation.refresh_from_db()
        return UnifiedService(self.account, self.conversation, use_llm=False)

    def _texto(self, texto):
        return self._bot().process_message(texto)

    def _clicar(self, reply_id):
        return self._bot().process_message('', interactive_reply={'id': reply_id, 'title': ''})

    def _sessao(self):
        return get_session_manager(self.profile, PHONE)

    def _envelhecer(self, horas):
        for s in CustomerSession.objects.filter(phone_number__contains='981549999'):
            data = dict(s.cart_data or {})
            antes = timezone.now() - timedelta(hours=horas)
            data['checkout_snapshots'] = [
                {**snap, 'at': antes.isoformat()} for snap in data.get('checkout_snapshots') or []
            ]
            s.cart_data = data
            s.save(update_fields=['cart_data'])

    def test_ola_dois_dias_depois_nao_e_observacao_nem_produto(self):
        self._envelhecer(48)

        self.assertFalse(self._sessao().is_waiting_for_notes())
        resposta = self._texto('Olá')
        conteudo = resposta.content or ''
        self.assertNotIn('Cebola roxa', conteudo)
        self.assertNotIn('não uma observação', conteudo)
        self.assertNotIn('Anotado', conteudo)

    def test_espera_de_endereco_velha_tambem_vence(self):
        self._sessao().set_waiting_for_address(True)
        self.assertTrue(espera_endereco(self.conversation, company=self.profile))
        self._envelhecer(48)

        self.assertFalse(espera_endereco(self.conversation, company=self.profile))
        self.assertFalse(self._sessao().is_waiting_for_address())

    def test_observacao_dentro_da_janela_continua_anotada(self):
        self._envelhecer(1)

        resposta = self._texto('sem cebola por favor')
        self.assertIn('Anotado', resposta.content or '')
