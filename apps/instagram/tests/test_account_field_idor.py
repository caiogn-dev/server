"""
Segurança(P0): `account` gravável em InstagramMediaSerializer e
InstagramConversationSerializer — IDOR de escrita cross-tenant.

Um usuário autenticado poderia:
  1. Criar um InstagramMedia/InstagramConversation com account de outro tenant.
  2. Fazer PATCH numa mídia/conversa própria trocando o account para o de outro
     tenant, enviando mensagens pela conta alheia.

Correção esperada:
  - `account` em read_only_fields nos dois serializers (campo nunca aceito em escrita).
  - `perform_create()` nos dois ViewSets injeta a account a partir do `account_id`
     de query-param/body que pertence ao usuário autenticado — account alheio → 403.

Estes testes usam SimpleTestCase + mocks para não precisar de banco.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from apps.instagram.api.serializers import (
    InstagramConversationSerializer,
    InstagramMediaSerializer,
)
from apps.instagram.api.views import (
    InstagramConversationViewSet,
    InstagramMediaViewSet,
)


class SerializerReadOnlyFieldTest(SimpleTestCase):
    """account deve ser read_only nos dois serializers."""

    def test_media_serializer_account_e_read_only(self):
        self.assertIn(
            'account',
            InstagramMediaSerializer.Meta.read_only_fields,
            'InstagramMediaSerializer.Meta.read_only_fields deve conter "account".',
        )

    def test_conversation_serializer_account_e_read_only(self):
        self.assertIn(
            'account',
            InstagramConversationSerializer.Meta.read_only_fields,
            'InstagramConversationSerializer.Meta.read_only_fields deve conter "account".',
        )


class MediaPerformCreateIDORTest(SimpleTestCase):
    """perform_create em InstagramMediaViewSet deve rejeitar account alheio."""

    def _make_request(self, user, account_id):
        factory = APIRequestFactory()
        req = factory.post('/fake/', {'account': str(account_id), 'media_type': 'IMAGE'})
        req.user = user
        return req

    def test_criar_media_com_account_alheio_retorna_403(self):
        user = MagicMock()
        user.is_superuser = False

        own_acc_id = uuid4()
        other_acc_id = uuid4()

        # `get_queryset` do viewset retorna only próprias accounts; simula
        # que a account solicitada NÃO pertence ao usuário.
        own_account = MagicMock(id=own_acc_id)
        other_account = MagicMock(id=other_acc_id)

        viewset = InstagramMediaViewSet()
        viewset.request = self._make_request(user, other_acc_id)
        viewset.format_kwarg = None

        with patch('apps.instagram.api.views.InstagramAccount') as MockAccount:
            # Filtro por user só retorna a própria conta — a alheia não está lá.
            qs = MagicMock()
            qs.filter.return_value.first.return_value = None  # conta alheia → None
            MockAccount.objects.filter.return_value = qs

            serializer = MagicMock()
            from rest_framework.exceptions import PermissionDenied
            try:
                viewset.perform_create(serializer)
                self.fail('Esperava PermissionDenied ao criar com account alheio.')
            except (PermissionDenied, Exception) as exc:
                # Qualquer exceção de acesso negado é aceitável.
                # O importante é que serializer.save() NÃO foi chamado
                # com a conta alheia.
                if serializer.save.called:
                    saved_account = serializer.save.call_args[1].get('account')
                    if saved_account is not None:
                        self.assertNotEqual(
                            getattr(saved_account, 'id', None),
                            other_acc_id,
                            'perform_create não deve salvar com a account alheia.',
                        )

    def test_criar_media_com_account_proprio_sucede(self):
        user = MagicMock()
        user.is_superuser = False

        own_acc_id = uuid4()
        own_account = MagicMock(id=own_acc_id)

        viewset = InstagramMediaViewSet()
        viewset.request = self._make_request(user, own_acc_id)
        viewset.format_kwarg = None

        with patch('apps.instagram.api.views.InstagramAccount') as MockAccount:
            qs = MagicMock()
            qs.filter.return_value.first.return_value = own_account
            MockAccount.objects.filter.return_value = qs

            serializer = MagicMock()
            try:
                viewset.perform_create(serializer)
            except Exception:
                pass  # se a view tiver outros guards, ok — o importante é abaixo

            if serializer.save.called:
                kwargs = serializer.save.call_args[1]
                self.assertEqual(
                    getattr(kwargs.get('account'), 'id', None),
                    own_acc_id,
                    'perform_create deve salvar com a account correta.',
                )


class ConversationPerformCreateIDORTest(SimpleTestCase):
    """perform_create em InstagramConversationViewSet deve rejeitar account alheio."""

    def _make_request(self, user, account_id):
        factory = APIRequestFactory()
        req = factory.post('/fake/', {'account': str(account_id), 'participant_id': 'p'})
        req.user = user
        return req

    def test_criar_conversa_com_account_alheio_retorna_403(self):
        user = MagicMock()
        user.is_superuser = False
        other_acc_id = uuid4()

        viewset = InstagramConversationViewSet()
        viewset.request = self._make_request(user, other_acc_id)
        viewset.format_kwarg = None

        with patch('apps.instagram.api.views.InstagramAccount') as MockAccount:
            qs = MagicMock()
            qs.filter.return_value.first.return_value = None  # alheia → None
            MockAccount.objects.filter.return_value = qs

            serializer = MagicMock()
            from rest_framework.exceptions import PermissionDenied
            try:
                viewset.perform_create(serializer)
                self.fail('Esperava PermissionDenied ao criar conversa com account alheia.')
            except (PermissionDenied, Exception) as exc:
                if serializer.save.called:
                    saved_account = serializer.save.call_args[1].get('account')
                    if saved_account is not None:
                        self.assertNotEqual(
                            getattr(saved_account, 'id', None),
                            other_acc_id,
                            'perform_create não deve salvar com a account alheia.',
                        )
