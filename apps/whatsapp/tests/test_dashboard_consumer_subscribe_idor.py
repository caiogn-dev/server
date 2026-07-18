"""Regressão de segurança: IDOR em subscribe_conversation do WhatsAppDashboardConsumer.

O WhatsAppConsumer já verificava acesso antes de assinar uma conversa, mas o
WhatsAppDashboardConsumer aceitava qualquer conversation_id sem verificação,
permitindo que qualquer usuário autenticado recebesse eventos em tempo real de
conversas alheias (PII: mensagens, telefones, nomes de clientes).

Cenários cobertos:
  1. subscribe_conversation de tenant alheio → retorna erro, não assina o grupo.
  2. subscribe_conversation da própria conta → assina o grupo normalmente.
  3. superuser pode assinar qualquer conversa.
  4. verify_conversation_access recusa IDs de contas alheias.
  5. verify_conversation_access aceita conversas das próprias contas.
  6. verify_conversation_access com superuser aceita qualquer conversa.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from django.test import SimpleTestCase

from apps.whatsapp.consumers import WhatsAppDashboardConsumer


def _make_consumer(user):
    """Cria uma instância de WhatsAppDashboardConsumer com scope e channel_layer mockados."""
    consumer = WhatsAppDashboardConsumer.__new__(WhatsAppDashboardConsumer)
    consumer.user = user
    consumer.account_groups = set()
    consumer.channel_name = 'test_channel'
    channel_layer = AsyncMock()
    channel_layer.group_add = AsyncMock()
    channel_layer.group_send = AsyncMock()
    consumer.channel_layer = channel_layer
    consumer.send_json = AsyncMock()
    return consumer


def _make_user(is_superuser=False):
    user = MagicMock()
    user.id = 42
    user.is_superuser = is_superuser
    return user


class TestDashboardConsumerSubscribeIDOR(SimpleTestCase):
    """subscribe_conversation deve verificar acesso antes de adicionar ao grupo."""

    def _run(self, coro):
        return asyncio.run(coro)

    # ── Cenário 1: acesso negado ─────────────────────────────────────────────

    def test_subscribe_alien_conversation_returns_error(self):
        """Conversa de tenant alheio → send_error chamado, group_add NÃO chamado."""
        user = _make_user()
        consumer = _make_consumer(user)
        consumer.send_error = AsyncMock()

        async def run():
            with patch.object(
                WhatsAppDashboardConsumer,
                'verify_conversation_access',
                new=AsyncMock(return_value=False),
            ):
                await consumer.handle_message({
                    'type': 'subscribe_conversation',
                    'conversation_id': 'alien-uuid',
                })
            consumer.send_error.assert_called_once()
            error_args = consumer.send_error.call_args[0]
            self.assertIn('acesso', error_args[0].lower())
            consumer.channel_layer.group_add.assert_not_called()

        self._run(run())

    def test_subscribe_alien_conversation_does_not_add_to_account_groups(self):
        """Acesso negado: group não é adicionado em account_groups."""
        user = _make_user()
        consumer = _make_consumer(user)
        consumer.send_error = AsyncMock()

        async def run():
            with patch.object(
                WhatsAppDashboardConsumer,
                'verify_conversation_access',
                new=AsyncMock(return_value=False),
            ):
                await consumer.handle_message({
                    'type': 'subscribe_conversation',
                    'conversation_id': 'alien-uuid',
                })
            self.assertNotIn('whatsapp_conv_alien-uuid', consumer.account_groups)

        self._run(run())

    # ── Cenário 2: acesso concedido ──────────────────────────────────────────

    def test_subscribe_own_conversation_adds_group(self):
        """Conversa própria → group_add chamado, subscribed enviado."""
        user = _make_user()
        consumer = _make_consumer(user)

        async def run():
            with patch.object(
                WhatsAppDashboardConsumer,
                'verify_conversation_access',
                new=AsyncMock(return_value=True),
            ):
                await consumer.handle_message({
                    'type': 'subscribe_conversation',
                    'conversation_id': 'own-uuid',
                })
            consumer.channel_layer.group_add.assert_called_once_with(
                'whatsapp_conv_own-uuid', 'test_channel'
            )
            self.assertIn('whatsapp_conv_own-uuid', consumer.account_groups)
            consumer.send_json.assert_called_once_with({
                'type': 'subscribed',
                'conversation_id': 'own-uuid',
            })

        self._run(run())

    # ── Cenário 3: superuser ─────────────────────────────────────────────────

    def test_superuser_subscribe_any_conversation(self):
        """Superuser: verify_conversation_access passa UUID arbitrário sem erro."""
        superuser = _make_user(is_superuser=True)
        consumer = _make_consumer(superuser)

        async def run():
            with patch.object(
                WhatsAppDashboardConsumer,
                'verify_conversation_access',
                new=AsyncMock(return_value=True),
            ):
                await consumer.handle_message({
                    'type': 'subscribe_conversation',
                    'conversation_id': 'any-uuid',
                })
            consumer.channel_layer.group_add.assert_called_once()

        self._run(run())

    # ── Cenário 4: verify_conversation_access — lógica de acesso ─────────────

    def test_verify_conversation_access_denies_alien_account(self):
        """Conversa de conta alheia → verify_conversation_access retorna False."""
        user = _make_user()
        consumer = _make_consumer(user)
        conv_id = 'conv-alien'

        with patch('apps.whatsapp.models.WhatsAppAccount') as MockAcc, \
             patch('apps.conversations.models.Conversation') as MockConv:
            MockAcc.objects.filter.return_value.values_list.return_value = ['own-account-id']
            MockConv.objects.filter.return_value.exists.return_value = False

            result = asyncio.run(consumer.verify_conversation_access(conv_id))

        self.assertFalse(result)

    def test_verify_conversation_access_grants_own_account(self):
        """Conversa da própria conta → verify_conversation_access retorna True."""
        user = _make_user()
        consumer = _make_consumer(user)
        conv_id = 'conv-own'

        with patch('apps.whatsapp.models.WhatsAppAccount') as MockAcc, \
             patch('apps.conversations.models.Conversation') as MockConv:
            MockAcc.objects.filter.return_value.values_list.return_value = ['own-account-id']
            MockConv.objects.filter.return_value.exists.return_value = True

            result = asyncio.run(consumer.verify_conversation_access(conv_id))

        self.assertTrue(result)

    def test_verify_conversation_access_superuser_any(self):
        """Superuser → verify_conversation_access retorna True sem checar owner."""
        superuser = _make_user(is_superuser=True)
        consumer = _make_consumer(superuser)

        with patch('apps.conversations.models.Conversation') as MockConv:
            MockConv.objects.filter.return_value.exists.return_value = True
            result = asyncio.run(consumer.verify_conversation_access('any-uuid'))

        self.assertTrue(result)
