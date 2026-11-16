from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.messaging.models import MessengerAccount, MessengerConversation, MessengerMessage


class MessengerConversationApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="messenger-tester",
            email="messenger@example.com",
            password="pass",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.account = MessengerAccount.objects.create(
            user=self.user,
            page_id="page-123",
            page_name="Test Page",
            page_access_token="token",
            is_active=True,
        )
        self.conversation = MessengerConversation.objects.create(
            account=self.account,
            psid="psid-123",
            participant_name="Cliente",
            unread_count=1,
        )

    @patch("apps.messaging.api.views.MessengerPlatformService.send_text_message")
    def test_send_message_uses_platform_service(self, mock_send_text):
        mock_send_text.return_value = {"message_id": "mid.123"}

        url = reverse("messaging:messenger-conversations-send-message", args=[self.conversation.id])
        response = self.client.post(url, {"content": "Oi", "message_type": "text"}, format="json")

        self.assertEqual(response.status_code, 201)
        mock_send_text.assert_called_once_with("psid-123", "Oi")
        message = MessengerMessage.objects.get(conversation=self.conversation, is_from_page=True)
        self.assertEqual(message.content, "Oi")
        self.assertEqual(message.messenger_message_id, "mid.123")

    @patch("apps.messaging.services.MessengerService.mark_seen")
    def test_mark_read_clears_unread_messages(self, mock_mark_seen):
        MessengerMessage.objects.create(
            conversation=self.conversation,
            message_type="TEXT",
            content="Mensagem inbound",
            is_from_page=False,
            is_read=False,
        )

        url = reverse("messaging:messenger-conversations-mark-read", args=[self.conversation.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        mock_mark_seen.assert_called_once_with("psid-123")
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.unread_count, 0)
        self.assertFalse(
            MessengerMessage.objects.filter(conversation=self.conversation, is_read=False).exists()
        )


class MessengerAccountEncryptionTests(TestCase):
    """A2 — segredos do Messenger criptografados em repouso."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="enc-tester", email="enc@example.com", password="pass",
        )

    def test_secrets_stored_encrypted_but_read_plaintext(self):
        from django.db import connection

        account = MessengerAccount.objects.create(
            user=self.user,
            page_id="page-enc",
            page_name="Enc Page",
            page_access_token="EAAG-super-secret-page-token",
            app_secret="my-app-secret",
            is_active=True,
        )

        # Leitura via ORM devolve o plaintext.
        account.refresh_from_db()
        self.assertEqual(account.page_access_token, "EAAG-super-secret-page-token")
        self.assertEqual(account.app_secret, "my-app-secret")

        # No banco, o valor cru está criptografado (Fernet → começa com gAAA).
        with connection.cursor() as cur:
            cur.execute(
                "SELECT page_access_token, app_secret FROM messenger_accounts WHERE id = %s",
                [str(account.id)],
            )
            raw_token, raw_secret = cur.fetchone()
        self.assertTrue(raw_token.startswith("gAAA"), raw_token)
        self.assertNotIn("super-secret", raw_token)
        self.assertTrue(raw_secret.startswith("gAAA"), raw_secret)
        self.assertNotIn("my-app-secret", raw_secret)


class MessengerConversationAccountScopeTests(TestCase):
    """O campo `account` da conversa só aceita contas do próprio usuário."""

    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="msg-owner", email="owner@example.com", password="pass"
        )
        self.attacker = user_model.objects.create_user(
            username="msg-attacker", email="attacker@example.com", password="pass"
        )
        self.owner_account = MessengerAccount.objects.create(
            user=self.owner, page_id="page-owner", page_name="Owner", page_access_token="t"
        )
        self.attacker_account = MessengerAccount.objects.create(
            user=self.attacker, page_id="page-att", page_name="Att", page_access_token="t"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.attacker)

    def test_cannot_create_conversation_in_foreign_account(self):
        url = reverse("messaging:messenger-conversations-list")
        response = self.client.post(
            url, {"account": str(self.owner_account.id), "psid": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            MessengerConversation.objects.filter(account=self.owner_account).exists()
        )

    def test_cannot_move_conversation_to_foreign_account(self):
        conv = MessengerConversation.objects.create(account=self.attacker_account, psid="p")
        url = reverse("messaging:messenger-conversations-detail", args=[conv.id])
        response = self.client.patch(
            url, {"account": str(self.owner_account.id)}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        conv.refresh_from_db()
        self.assertEqual(conv.account_id, self.attacker_account.id)

    def test_can_create_conversation_in_own_account(self):
        url = reverse("messaging:messenger-conversations-list")
        response = self.client.post(
            url, {"account": str(self.attacker_account.id), "psid": "ok"}, format="json"
        )
        self.assertEqual(response.status_code, 201)


class MessengerConversationListQueryCountTests(TestCase):
    """A lista de conversas não faz queries por conversa (N+1 da última mensagem)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="msg-perf", email="perf@example.com", password="pass"
        )
        self.account = MessengerAccount.objects.create(
            user=self.user, page_id="page-perf", page_name="Perf", page_access_token="t"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _criar(self, n, offset=0):
        for i in range(offset, offset + n):
            conv = MessengerConversation.objects.create(account=self.account, psid=f"psid-{i}")
            MessengerMessage.objects.create(conversation=conv, content=f"antiga {i}", is_from_page=False)
            MessengerMessage.objects.create(conversation=conv, content=f"recente {i}", is_from_page=False)

    def _contar(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        url = reverse("messaging:messenger-conversations-list")
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        rows = data["results"] if isinstance(data, dict) and "results" in data else data
        return len(ctx), rows

    def test_numero_de_queries_nao_cresce_com_conversas(self):
        self._criar(2)
        q2, _ = self._contar()
        self._criar(4, offset=2)
        q6, rows = self._contar()
        self.assertEqual(q2, q6)
        self.assertEqual(len(rows), 6)
        for row in rows:
            self.assertTrue(row["last_message"]["content"].startswith("recente"))
            self.assertTrue(row["last_message_preview"].startswith("recente"))
