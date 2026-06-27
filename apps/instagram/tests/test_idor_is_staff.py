"""
Testes de segurança: IDOR via is_staff no Instagram (cross-tenant).

Garante que usuários com is_staff=True NÃO vejam dados de contas Instagram
alheias. Apenas is_superuser deve ter acesso cross-tenant.

Cenário atacante:
  - user_a: dono de uma loja/conta Instagram
  - user_b: staff (is_staff=True) de outro tenant — NÃO pode ver dados de user_a
  - superuser: admin de plataforma — PODE ver todos os dados
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.instagram.models import InstagramAccount, InstagramConversation, InstagramLive, InstagramMedia

User = get_user_model()


def _items(response):
    """Extrai lista de itens de resposta paginada ou não paginada do DRF."""
    data = response.data
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


def _make_account(user, username="ig_user"):
    return InstagramAccount.objects.create(
        user=user,
        username=username,
        access_token="fake-token",
        instagram_business_id=f"ig_{username}",
    )


def _make_conversation(account, participant="ext_user_1"):
    return InstagramConversation.objects.create(
        account=account,
        participant_id=participant,
        participant_username=participant,
        is_active=True,
    )


class InstagramStaffIDORTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_a = User.objects.create_user(username="user_a", password="pw")
        self.user_b = User.objects.create_user(username="user_b", password="pw", is_staff=True)
        self.superuser = User.objects.create_superuser(username="super", password="pw")

        self.account_a = _make_account(self.user_a, username="acct_a")
        self.account_b = _make_account(self.user_b, username="acct_b")

    # ── InstagramAccountViewSet ──────────────────────────────────────────────

    def test_staff_ve_apenas_propria_conta(self):
        """staff NÃO deve ver conta de outro usuário."""
        self.client.force_authenticate(self.user_b)
        r = self.client.get("/api/v1/instagram/accounts/")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in _items(r)]
        self.assertIn(str(self.account_b.id), ids)
        self.assertNotIn(str(self.account_a.id), ids)

    def test_superuser_ve_todas_as_contas(self):
        """superuser deve ver todas as contas."""
        self.client.force_authenticate(self.superuser)
        r = self.client.get("/api/v1/instagram/accounts/")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in _items(r)]
        self.assertIn(str(self.account_a.id), ids)
        self.assertIn(str(self.account_b.id), ids)

    def test_staff_nao_acessa_detalhe_de_conta_alheia(self):
        """staff NÃO deve acessar detalhe de conta de outro usuário."""
        self.client.force_authenticate(self.user_b)
        r = self.client.get(f"/api/v1/instagram/accounts/{self.account_a.id}/")
        self.assertEqual(r.status_code, 404)

    # ── InstagramMediaViewSet ────────────────────────────────────────────────

    def test_staff_ve_apenas_propria_midia(self):
        """staff NÃO deve ver mídia de contas alheias."""
        media_a = InstagramMedia.objects.create(
            account=self.account_a,
            instagram_media_id="media_a",
            media_type="IMAGE",
            permalink="https://instagram.com/p/a",
        )
        media_b = InstagramMedia.objects.create(
            account=self.account_b,
            instagram_media_id="media_b",
            media_type="IMAGE",
            permalink="https://instagram.com/p/b",
        )
        self.client.force_authenticate(self.user_b)
        r = self.client.get("/api/v1/instagram/media/")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in _items(r)]
        self.assertIn(str(media_b.id), ids)
        self.assertNotIn(str(media_a.id), ids)

    # ── InstagramLiveViewSet ─────────────────────────────────────────────────

    def test_staff_ve_apenas_propria_live(self):
        """staff NÃO deve ver lives de contas alheias."""
        live_a = InstagramLive.objects.create(
            account=self.account_a,
            live_id="live_a",
            title="Live A",
        )
        live_b = InstagramLive.objects.create(
            account=self.account_b,
            live_id="live_b",
            title="Live B",
        )
        self.client.force_authenticate(self.user_b)
        r = self.client.get("/api/v1/instagram/live/")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in _items(r)]
        self.assertIn(str(live_b.id), ids)
        self.assertNotIn(str(live_a.id), ids)

    # ── InstagramConversationViewSet ─────────────────────────────────────────

    def test_staff_nao_ve_conversas_de_outra_conta(self):
        """staff NÃO deve ver conversas DM de contas Instagram alheias."""
        conv_a = _make_conversation(self.account_a, participant="ext_1")
        conv_b = _make_conversation(self.account_b, participant="ext_2")

        self.client.force_authenticate(self.user_b)
        r = self.client.get("/api/v1/instagram/conversations/")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in _items(r)]
        self.assertIn(str(conv_b.id), ids)
        self.assertNotIn(str(conv_a.id), ids)

    def test_staff_nao_acessa_detalhe_de_conversa_alheia(self):
        """staff NÃO deve acessar detalhe de conversa de outra conta."""
        conv_a = _make_conversation(self.account_a, participant="ext_1")
        self.client.force_authenticate(self.user_b)
        r = self.client.get(f"/api/v1/instagram/conversations/{conv_a.id}/")
        self.assertEqual(r.status_code, 404)

    def test_conversa_filtrada_por_account_nao_expoe_dados_alheios(self):
        """Passar account=<conta-alheia> na query string NÃO deve retornar dados."""
        conv_a = _make_conversation(self.account_a, participant="ext_1")
        self.client.force_authenticate(self.user_b)
        r = self.client.get(f"/api/v1/instagram/conversations/?account={self.account_a.id}")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in _items(r)]
        self.assertNotIn(str(conv_a.id), ids)

    def test_superuser_ve_todas_as_conversas(self):
        """superuser deve poder ver conversas de qualquer conta."""
        conv_a = _make_conversation(self.account_a, participant="ext_1")
        conv_b = _make_conversation(self.account_b, participant="ext_2")
        self.client.force_authenticate(self.superuser)
        r = self.client.get("/api/v1/instagram/conversations/")
        self.assertEqual(r.status_code, 200)
        ids = [item["id"] for item in _items(r)]
        self.assertIn(str(conv_a.id), ids)
        self.assertIn(str(conv_b.id), ids)
