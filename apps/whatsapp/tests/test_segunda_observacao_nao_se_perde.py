"""A segunda observação antes de pagar também é observação.

25/09, Cê Saladas: com o resumo na tela ela escreveu "Sem tomate cereja
também" (anotado) e em seguida "Acrescenta cenoura ralada" — que caiu em
"Como posso te ajudar? 👇". A primeira nota desligava a espera de observação,
e a segunda virava mensagem desconhecida. Ela desistiu e chamou o atendente.

Contrato: enquanto o pagamento não foi escolhido, cada texto de observação
SOMA à anterior; o pedido nasce com todas.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '5563981545075'


class SegundaObservacaoTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-ce-obs2', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-obs2', owner=owner,
        )
        self.account = WhatsAppAccount.objects.create(name='CeObs2', phone_number_id='PHOBS2', waba_id='WOBS2')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        StoreProduct.objects.create(store=self.store, name='Especial Filé de Frango', slug='especial', price=39.99, is_active=True)
        self.handler = InteractiveReplyHandler(self.account, self.conversation, self.profile)
        self.handler._get_session_manager().set_waiting_for_notes(True)

    @property
    def sessao(self):
        # Gerente NOVO a cada leitura: cada um guarda a sessão em cache, e ler
        # pelo de setUp devolveria o estado de antes do handler gravar.
        return self.handler._get_session_manager()

    def test_duas_observacoes_somam(self):
        self.handler._handle_notes_input('Sem tomate cereja também')
        self.assertTrue(self.sessao.is_waiting_for_notes(), 'a 1ª nota não pode fechar a porta da 2ª')

        self.handler._handle_notes_input('Acrescenta cenoura ralada')

        self.assertEqual(self.sessao.get_customer_notes(), 'Sem tomate cereja também; Acrescenta cenoura ralada')

    def test_palavra_de_pular_nao_apaga_o_que_ja_foi_anotado(self):
        self.handler._handle_notes_input('sem cebola')
        self.handler._handle_notes_input('não')
        self.assertEqual(self.sessao.get_customer_notes(), 'sem cebola')
