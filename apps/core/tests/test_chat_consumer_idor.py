"""Regressão de segurança: IDOR em ChatConsumer (ws/chat/{conversation_id}/).

Antes do fix, _post_auth_connect entrava no grupo chat_{conversation_id} sem
verificar se a conversa pertence a uma conta do usuário autenticado. Além disso,
mark_message_read atualizava mensagens de qualquer tenant sem verificação.

Vetor de ataque:
  1. Usuário da loja A conecta em ws/chat/<uuid_de_conversa_da_loja_B>/
  2. Passa a receber mensagens, typing e status em tempo real da loja B (PII completo)
  3. Pode marcar mensagens da loja B como lidas via {type: read}

Fix:
  - _post_auth_connect verifica verify_conversation_access antes de group_add
  - Acesso negado fecha a conexão com código 4003
  - mark_message_read verifica owned_ids antes de atualizar; retorno silencioso se negado

Testes sem PostgreSQL/Docker (SimpleTestCase + inspeção de código-fonte).
"""
import inspect

from django.test import SimpleTestCase


class TestChatConsumerConnectionIDOR(SimpleTestCase):
    """Verifica que _post_auth_connect aplica gate de tenant antes de group_add."""

    def _source(self):
        from apps.core.consumers import ChatConsumer
        return inspect.getsource(ChatConsumer._post_auth_connect)

    def test_verify_conversation_access_chamado(self):
        """_post_auth_connect deve chamar verify_conversation_access."""
        self.assertIn('verify_conversation_access', self._source())

    def test_verify_antes_de_group_add(self):
        """verify_conversation_access deve ser invocado ANTES de group_add."""
        src = self._source()
        idx_verify = src.index('verify_conversation_access')
        idx_add = src.index('group_add')
        self.assertLess(
            idx_verify, idx_add,
            "verify_conversation_access deve preceder group_add no _post_auth_connect",
        )

    def test_acesso_negado_fecha_4003(self):
        """Acesso negado deve fechar a conexão com código 4003."""
        self.assertIn('4003', self._source())


class TestChatConsumerVerifyConversationAccess(SimpleTestCase):
    """Verifica a estrutura do método verify_conversation_access."""

    def _source(self):
        from apps.core.consumers import ChatConsumer
        return inspect.getsource(ChatConsumer.verify_conversation_access)

    def test_metodo_existe(self):
        """ChatConsumer deve ter o método verify_conversation_access."""
        from apps.core.consumers import ChatConsumer
        self.assertTrue(
            hasattr(ChatConsumer, 'verify_conversation_access'),
            "ChatConsumer não tem verify_conversation_access",
        )

    def test_superuser_bypassa_filtro(self):
        """Superuser não é filtrado por account_id__in."""
        src = self._source()
        self.assertIn('is_superuser', src)

    def test_filtra_por_account_id(self):
        """Usuário comum tem acesso filtrado via account_id."""
        src = self._source()
        self.assertIn('account_id__in', src)
        self.assertIn('owner=self.user', src)


class TestChatConsumerMarkMessageReadIDOR(SimpleTestCase):
    """Verifica que mark_message_read valida posse da conta antes de atualizar."""

    def _source(self):
        from apps.core.consumers import ChatConsumer
        return inspect.getsource(ChatConsumer.mark_message_read)

    def test_verifica_is_superuser(self):
        """mark_message_read deve ter gate de superuser."""
        self.assertIn('is_superuser', self._source())

    def test_verifica_owned_ids(self):
        """mark_message_read deve construir conjunto de IDs acessíveis."""
        self.assertIn('owned_ids', self._source())

    def test_retorno_silencioso_acesso_negado(self):
        """Acesso negado deve retornar sem atualizar (sem exceção)."""
        src = self._source()
        # Deve haver um 'return' early quando a conta não pertence ao usuário
        self.assertIn('return', src)

    def test_usa_select_related(self):
        """mark_message_read deve usar select_related para evitar N+1."""
        self.assertIn('select_related', self._source())

    def test_nao_salva_sem_verificacao(self):
        """O campo 'save' deve aparecer após a verificação de owned_ids."""
        src = self._source()
        idx_owned = src.index('owned_ids')
        idx_save = src.index('save')
        self.assertLess(
            idx_owned, idx_save,
            "owned_ids deve preceder save no mark_message_read",
        )
