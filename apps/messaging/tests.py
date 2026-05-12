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
