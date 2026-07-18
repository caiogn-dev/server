"""Regressão de segurança: IDOR em InstagramConsumer.subscribe_conversation.

Antes do fix, handle_message aceitava subscribe_conversation sem verificar
se a conversa pertence à conta Instagram conectada. Vetor idêntico ao do
WhatsAppDashboardConsumer corrigido em PR #305.

Vetor de ataque:
  1. Usuário autentica com conta Instagram própria → ws/instagram/{account_id}/
  2. Envia {type: subscribe_conversation, conversation_id: <uuid_alheio>}
  3. Passa a receber typing, mensagens e seen status de conversa de outro tenant

Fix:
  - subscribe_conversation verifica verify_instagram_conversation_access antes de group_add
  - Acesso negado retorna {type: error, code: forbidden}
  - verify_instagram_conversation_access filtra InstagramConversation por account_id=self.account_id

Testes sem PostgreSQL/Docker (SimpleTestCase + inspeção de código-fonte).
"""
import inspect

from django.test import SimpleTestCase


class TestInstagramConsumerSubscribeIDOR(SimpleTestCase):
    """Verifica que subscribe_conversation aplica gate de tenant antes de group_add."""

    def _handler_source(self):
        from apps.instagram.consumers import InstagramConsumer
        return inspect.getsource(InstagramConsumer.handle_message)

    def test_verify_instagram_conversation_access_chamado(self):
        """handle_message deve chamar verify_instagram_conversation_access."""
        self.assertIn('verify_instagram_conversation_access', self._handler_source())

    def test_verify_antes_de_group_add_no_subscribe(self):
        """verify_instagram_conversation_access deve preceder group_add em subscribe_conversation."""
        src = self._handler_source()
        idx_verify = src.index('verify_instagram_conversation_access')
        idx_add = src.index('group_add')
        self.assertLess(
            idx_verify, idx_add,
            "verify_instagram_conversation_access deve preceder group_add",
        )

    def test_acesso_negado_envia_forbidden(self):
        """Acesso negado deve retornar resposta com code=forbidden."""
        self.assertIn('forbidden', self._handler_source())

    def test_acesso_negado_nao_adiciona_grupo(self):
        """Acesso negado deve retornar antes de group_add."""
        src = self._handler_source()
        idx_verify = src.index('verify_instagram_conversation_access')
        idx_return = src.index('return', idx_verify)
        idx_add = src.index('group_add', idx_verify)
        self.assertLess(
            idx_return, idx_add,
            "Deve haver return antes do group_add quando acesso negado",
        )


class TestInstagramConsumerVerifyConversationAccess(SimpleTestCase):
    """Verifica a estrutura do método verify_instagram_conversation_access."""

    def _source(self):
        from apps.instagram.consumers import InstagramConsumer
        return inspect.getsource(InstagramConsumer.verify_instagram_conversation_access)

    def test_metodo_existe(self):
        """InstagramConsumer deve ter o método verify_instagram_conversation_access."""
        from apps.instagram.consumers import InstagramConsumer
        self.assertTrue(
            hasattr(InstagramConsumer, 'verify_instagram_conversation_access'),
            "InstagramConsumer não tem verify_instagram_conversation_access",
        )

    def test_superuser_bypassa_filtro(self):
        """Superuser não é filtrado por account_id."""
        self.assertIn('is_superuser', self._source())

    def test_filtra_por_account_id_da_conta_conectada(self):
        """Usuário comum é filtrado pela conta já autenticada."""
        self.assertIn('account_id=self.account_id', self._source())

    def test_usa_instagram_conversation_model(self):
        """verify_instagram_conversation_access deve consultar InstagramConversation."""
        self.assertIn('InstagramConversation', self._source())

    def test_check_exists_retorna_bool(self):
        """A query deve terminar com .exists() retornando booleano."""
        self.assertIn('exists()', self._source())
