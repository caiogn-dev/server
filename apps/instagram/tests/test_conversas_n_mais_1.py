"""Lista de conversas do Instagram não pode fazer queries por conversa."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.instagram.models import InstagramAccount, InstagramConversation, InstagramMessage

User = get_user_model()


def _items(r):
    return r.data["results"] if isinstance(r.data, dict) and "results" in r.data else r.data


class ConversasNMaisUmTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ig_n1", password="x", email="n1@x.com")
        self.acc = InstagramAccount.objects.create(
            user=self.user, username="n1", access_token="t", instagram_business_id="ig_n1")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _conv(self, i, with_msgs=True):
        c = InstagramConversation.objects.create(
            account=self.acc, participant_id=f"p{i}", participant_username=f"u{i}")
        if with_msgs:
            InstagramMessage.objects.create(conversation=c, message_type="TEXT", content=f"antiga{i}")
            InstagramMessage.objects.create(conversation=c, message_type="TEXT", content=f"nova{i}")
            InstagramMessage.objects.create(
                conversation=c, message_type="TEXT", content=f"desfeita{i}", is_unsent=True)
        return c

    def _count(self):
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get("/api/v1/instagram/conversations/")
        self.assertEqual(r.status_code, 200, r.content)
        return len(ctx), _items(r)

    def test_queries_constantes(self):
        for i in range(2):
            self._conv(i)
        q2, _ = self._count()
        for i in range(2, 8):
            self._conv(i)
        q8, items = self._count()
        self.assertEqual(len(items), 8)
        self.assertEqual(q2, q8)

    def test_conteudo_ignora_mensagem_desfeita(self):
        self._conv(1)
        self._conv(2, with_msgs=False)
        _, items = self._count()
        by_user = {i["last_message_preview"] for i in items}
        self.assertIn("", by_user)
        previews = [i for i in items if i["last_message"]]
        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0]["last_message"]["type"], "TEXT")
        self.assertEqual(previews[0]["last_message_preview"], "nova1")
