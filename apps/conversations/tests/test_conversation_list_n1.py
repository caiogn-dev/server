"""Regressão N+1 na listagem de conversas (inbox).

O ConversationSerializer fazia, POR conversa: 3 queries em whatsapp_messages
(message_count/last_preview/unread_count) + 1 no handover (OneToOne) → N+1.
Agora: handover via select_related; contagens/preview via annotate/Subquery no
viewset. Prova O(1) com 2 pontos de dados (3 e 9 conversas).
"""
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APITestCase

from apps.conversations.models import Conversation
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class ConversationListNoN1Test(APITestCase):
    def _account(self, suffix):
        return WhatsAppAccount.objects.create(
            name=f'acc-{suffix}', phone_number_id=f'pn-{suffix}', waba_id=f'wa-{suffix}',
            phone_number=f'+55{suffix}', display_phone_number=f'+55{suffix}',
            access_token_encrypted='x', webhook_verify_token='x',
        )

    def _conversations(self, account, n, tag):
        for i in range(n):
            Conversation.objects.create(
                account=account, phone_number=f'+5511{tag}{i:04d}', contact_name=f'C{i}',
                wa_id=f'wa{tag}{i}', profile_picture_url='', agent_session_id='',
            )

    def _count_queries(self, n, tag):
        acc = self._account(tag)
        self._conversations(acc, n, tag)
        # superuser vê todas as conversas (sem precisar de vínculo de conta)
        su = User.objects.create_superuser(username=f'su-{tag}', email=f'su-{tag}@t.com', password='x')
        self.client.force_authenticate(su)
        url = '/api/v1/conversations/?page_size=100'
        self.client.get(url)  # warmup
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        return len(ctx.captured_queries)

    def test_query_count_constant_regardless_of_conversation_count(self):
        q3 = self._count_queries(3, 'a')
        q9 = self._count_queries(9, 'b')
        self.assertEqual(
            q3, q9,
            f'N+1 na listagem de conversas: 3 convs={q3} queries, 9 convs={q9} queries '
            f'(deveria ser constante).'
        )
