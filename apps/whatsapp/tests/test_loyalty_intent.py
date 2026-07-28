from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreLoyaltyAccount, StoreOrder
from apps.whatsapp.intents.detector import IntentDetector, IntentType
from apps.whatsapp.intents.handlers.loyalty import LoyaltyStatusHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class LoyaltyIntentDetectionTest(TestCase):
    def test_frases_de_fidelidade_detectadas(self):
        det = IntentDetector()
        for frase in ('quantos pontos eu tenho?', 'meu cartão fidelidade',
                      'quando ganho salada grátis', 'fidelidade'):
            intent = det.detect_regex(frase)
            assert intent == IntentType.LOYALTY_STATUS, f'{frase!r} -> {intent}'


class LoyaltyStatusHandlerPhoneVariantTest(TestCase):
    """Garante que o handler resolve o cliente mesmo quando o formato do
    telefone armazenado em StoreOrder.customer_phone diverge do wa_id bruto
    da conversa (ex.: sem o 55 do país, ou com dígito 9 a mais/a menos) —
    regressão do bug de match exato reportado na Fase 1 de Gamificação."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono_fidelidade', email='dono_fidelidade@loja.com', password='x'
        )
        self.store = Store.objects.create(
            billing_exempt=True,
            name='Loja Fidelidade', slug='loja-fidelidade', owner=self.owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='LojaFidelidade', phone_number_id='PHFID', waba_id='WFID',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.customer = User.objects.create_user(
            username='cliente_fidelidade', email='cliente_fidelidade@loja.com', password='x'
        )
        # wa_id bruto da conversa vem com "+" na frente (formato usado por
        # alguns canais/imports), enquanto o pedido foi salvo só com dígitos —
        # com filter(customer_phone=phone) exato os dois nunca batem.
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number='+5563996660000',
        )
        StoreOrder.objects.create(
            store=self.store,
            order_number='LOY-TEST-0001',
            customer=self.customer,
            customer_phone='5563996660000',
            customer_name='Cliente Fidelidade',
            status='delivered',
            subtotal=30,
            total=30,
        )
        StoreLoyaltyAccount.objects.create(
            store=self.store, user=self.customer,
            qualified_count=13, redeemed_count=0,
        )

    def test_resolve_cliente_com_telefone_em_formato_diferente(self):
        handler = LoyaltyStatusHandler(self.account, self.conversation, self.profile)
        resolved = handler._resolve_user()
        assert resolved == self.customer, (
            "Handler deveria resolver o cliente via variantes de telefone, "
            "não só match exato."
        )

    def test_handle_retorna_status_real_via_checkout_service(self):
        handler = LoyaltyStatusHandler(self.account, self.conversation, self.profile)
        result = handler.handle({})
        # threshold default = 10; qualified=13 → progress=3, 1 disponível.
        assert 'grátis para resgatar' in result.response_text
