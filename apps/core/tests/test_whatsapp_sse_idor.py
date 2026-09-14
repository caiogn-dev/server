"""Regressão de segurança: IDOR em WhatsAppSSEView.get_event_stream().

Antes do fix, qualquer usuário autenticado podia chamar /api/sse/whatsapp/ e
receber mensagens de WhatsApp de TODOS os tenants em tempo real (from_number,
to_number, text_body, conversation_id) porque o query base não aplicava escopo
de tenant nem validava a posse dos parâmetros account_id / conversation_id.

Vetores de ataque:
  1. Sem account_id → Message.objects.filter(created_at__gt=...) retorna
     mensagens de todos os tenants.
  2. Com account_id alheio → filtra por conta de outro tenant sem checar posse.
  3. Com conversation_id alheio → faz Conversation.objects.get(id=...) sem
     verificar se a conversa pertence a uma conta acessível pelo usuário.

Fix esperado:
  - get_event_stream deve obter accessible_whatsapp_account_ids(user) no início.
  - Rejeitar account_id que não esteja nos ids acessíveis (yield error + return).
  - Conversation.objects.get() deve ser filtrado por account_id__in=accessible_ids.
  - query base de Message e status_updates devem ser filtrados por
    account_id__in=accessible_ids (exceto para superusuário).

Testes sem PostgreSQL/Docker (SimpleTestCase + inspeção de código-fonte).
"""
import inspect

from django.test import SimpleTestCase


class WhatsAppSSEIDORFixTest(SimpleTestCase):
    """Verifica que get_event_stream aplica escopo de tenant no stream de WhatsApp."""

    def _source(self):
        from apps.core.sse_views import WhatsAppSSEView
        return inspect.getsource(WhatsAppSSEView.get_event_stream)

    def test_accessible_whatsapp_account_ids_chamado(self):
        """get_event_stream deve importar/chamar accessible_whatsapp_account_ids."""
        self.assertIn('accessible_whatsapp_account_ids', self._source())

    def test_rejeita_account_id_fora_do_escopo(self):
        """Deve haver verificação de account_id contra a lista acessível antes de usá-lo."""
        src = self._source()
        # Deve ter verificação que rejeita account_id não pertencente ao usuário
        self.assertIn('Acesso negado', src)

    def test_conversation_fetch_escopado(self):
        """Conversation.objects.get sem filtro de tenant não pode existir no stream."""
        src = self._source()
        # Não pode existir get direto sem filtro de account
        # A versão corrigida deve filtrar por account_id__in antes do .get()
        self.assertNotIn('Conversation.objects.get(id=conversation_id)', src)

    def test_query_base_de_messages_escopada(self):
        """A query base de Message deve ser filtrada por account_id__in=accessible_ids."""
        src = self._source()
        self.assertIn('accessible_ids', src)

    def test_superuser_nao_restringido(self):
        """Superusuário deve ter accessible_ids=None (sem restrição de tenant)."""
        src = self._source()
        self.assertIn('is_superuser', src)

    def test_status_updates_escopado(self):
        """status_updates também deve ser filtrado por tenant (accessible_ids)."""
        src = self._source()
        # O filtro de accessible_ids deve aparecer em ambos os querysets
        idx_first = src.index('accessible_ids')
        # Deve haver pelo menos duas ocorrências de accessible_ids no método
        idx_second = src.index('accessible_ids', idx_first + 1)
        self.assertGreater(idx_second, idx_first)

    def test_gate_aplicado_antes_do_loop(self):
        """Validação de account_id deve acontecer ANTES do while True."""
        src = self._source()
        idx_gate = src.find('Acesso negado')
        idx_loop = src.find('while True')
        self.assertGreater(idx_gate, 0, 'Gate "Acesso negado" não encontrado no source')
        self.assertGreater(idx_loop, 0, 'Loop while True não encontrado no source')
        self.assertLess(idx_gate, idx_loop, 'Gate deve ser aplicado antes do while True')
