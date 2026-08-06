"""O inbox tem que vir da conversa mais recente para a mais antiga.

`_accessible_conversations` usa `annotate(Count('messages'))` para matar o N+1
do serializer. Query com agregação faz o Django DESCARTAR o `ordering` do
Meta — a lista voltava na ordem arbitrária do Postgres e o DRF ainda avisava
(`UnorderedObjectListWarning`). Com paginação de 20, a conversa que acabou de
chegar caía numa página qualquer.

06/ago: a conversa da Lúcia (13:18) não aparecia e o topo do painel mostrava a
Juliana, de 05/ago.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.conversations.api.views import _accessible_conversations
from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class InboxOrdenacaoTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin-inbox', password='x', email='admin-inbox@real.com',
        )
        self.account = WhatsAppAccount.objects.create(
            name='Conta Inbox', phone_number_id='999', waba_id='888',
            access_token='t', phone_number='5563000000001',
        )
        agora = timezone.now()
        # Criadas fora de ordem de propósito.
        self.antiga = Conversation.objects.create(
            account=self.account, phone_number='556300000001',
            contact_name='Juliana', last_message_at=agora - timedelta(days=8),
        )
        self.recente = Conversation.objects.create(
            account=self.account, phone_number='556300000002',
            contact_name='Lúcia', last_message_at=agora,
        )
        self.meio = Conversation.objects.create(
            account=self.account, phone_number='556300000003',
            contact_name='Elisa', last_message_at=agora - timedelta(days=1),
        )
        self.sem_mensagem = Conversation.objects.create(
            account=self.account, phone_number='556300000004',
            contact_name='Nunca falou', last_message_at=None,
        )

    def test_queryset_declara_estar_ordenado(self):
        """DRF emite UnorderedObjectListWarning quando `ordered` é False."""
        self.assertTrue(_accessible_conversations(self.admin).ordered)

    def _nomes_da_conta(self):
        # O banco de teste é compartilhado e tem resíduo de outras suítes;
        # o superusuário enxerga tudo. Escopar à conta criada aqui.
        return list(
            _accessible_conversations(self.admin)
            .filter(account=self.account)
            .values_list('contact_name', flat=True)
        )

    def test_mais_recente_primeiro(self):
        self.assertEqual(self._nomes_da_conta()[:3], ['Lúcia', 'Elisa', 'Juliana'])

    def test_conversa_sem_mensagem_nao_fura_a_fila(self):
        """No Postgres, DESC coloca NULL primeiro — nulls_last conserta."""
        self.assertEqual(
            self._nomes_da_conta()[-1], 'Nunca falou',
            'conversa sem nenhuma mensagem foi parar no topo do inbox',
        )
