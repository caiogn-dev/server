"""Regressão N+1: AgentConversationSerializer.messages dispara 1 query extra por conversa.

AgentConversationSerializer declara `messages = AgentMessageSerializer(many=True)` —
relação reversa que aciona `obj.messages.all()` por linha sem prefetch.

Dois pontos afetados em agents/views.py:
  1. AgentViewSet.conversations  (linha ~204) — action sem prefetch
  2. AgentConversationViewSet.get_queryset (linha ~295) — queryset sem prefetch

Teste usa leitura de fonte (sem importar o módulo) para evitar dependência
transitiva de langchain_core/psycopg2 não instalados no container de CI.
"""
import os
import re
from django.test import SimpleTestCase

_VIEWS_PATH = os.path.join(os.path.dirname(__file__), '..', 'views.py')
_SERIALIZERS_PATH = os.path.join(os.path.dirname(__file__), '..', 'serializers.py')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _extract_block(source, header_pattern):
    """Extrai o corpo de um método/action identificado por header_pattern."""
    lines = source.splitlines()
    start = None
    base_indent = None
    block = []
    for line in lines:
        if start is None:
            if re.search(header_pattern, line):
                start = True
                base_indent = len(line) - len(line.lstrip())
                block.append(line)
        else:
            if line.strip() == '':
                block.append(line)
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= base_indent and line.strip():
                break
            block.append(line)
    return '\n'.join(block)


class AgentConversationSerializerHasNestedMessagesTest(SimpleTestCase):
    """Confirma que o serializer de conversas inclui `messages` aninhado."""

    def test_messages_field_is_nested_serializer(self):
        src = _read(_SERIALIZERS_PATH)
        self.assertIn(
            'messages = AgentMessageSerializer(many=True',
            src,
            'AgentConversationSerializer deve ter campo messages aninhado (gerador de N+1).',
        )


class AgentViewSetConversationsActionPrefetchTest(SimpleTestCase):
    """AgentViewSet.conversations action deve usar prefetch_related('messages')."""

    def setUp(self):
        self.src = _read(_VIEWS_PATH)

    def test_conversations_action_exists(self):
        self.assertIn(
            "def conversations(self, request",
            self.src,
            'AgentViewSet.conversations action não encontrada.',
        )

    def test_conversations_action_has_prefetch_messages(self):
        block = _extract_block(self.src, r'def conversations\s*\(self.*request')
        self.assertIn(
            "prefetch_related('messages')",
            block,
            "AgentViewSet.conversations deve chamar .prefetch_related('messages') "
            "para evitar N+1 ao serializar AgentConversationSerializer.",
        )

    def test_conversations_action_filters_by_agent(self):
        block = _extract_block(self.src, r'def conversations\s*\(self.*request')
        self.assertIn(
            '.filter(agent=agent)',
            block,
            'AgentViewSet.conversations deve filtrar por agent.',
        )

    def test_conversations_action_orders_by_last_message(self):
        block = _extract_block(self.src, r'def conversations\s*\(self.*request')
        self.assertIn(
            "order_by('-last_message_at')",
            block,
            "AgentViewSet.conversations deve manter order_by('-last_message_at').",
        )


class AgentConversationViewSetGetQuerysetPrefetchTest(SimpleTestCase):
    """AgentConversationViewSet.get_queryset aplica prefetch_related('messages')
    apenas nas actions list/retrieve que serializam mensagens aninhadas.
    history e clear_memory acessam apenas Redis — prefetch seria desperdício."""

    def setUp(self):
        self.src = _read(_VIEWS_PATH)
        self.viewset_block = self.src.split('class AgentConversationViewSet')[1]
        self.get_qs_block = _extract_block(self.viewset_block, r'def get_queryset\s*\(self\)')

    def test_get_queryset_exists_in_viewset(self):
        self.assertIn(
            'class AgentConversationViewSet',
            self.src,
            'AgentConversationViewSet não encontrado.',
        )

    def test_get_queryset_has_prefetch_messages(self):
        self.assertIn(
            "prefetch_related('messages')",
            self.get_qs_block,
            "AgentConversationViewSet.get_queryset deve chamar .prefetch_related('messages') "
            "para evitar N+1 em list/retrieve.",
        )

    def test_get_queryset_prefetch_conditional_on_list_retrieve(self):
        """prefetch deve ser aplicado condicionalmente (action in list/retrieve)
        para não carregar mensagens desnecessariamente em history/clear_memory."""
        self.assertIn(
            "'action'",
            self.get_qs_block,
            "AgentConversationViewSet.get_queryset deve verificar a action antes do prefetch.",
        )
        self.assertIn(
            "'list'",
            self.get_qs_block,
            "Condição deve incluir 'list' para prefetch.",
        )
        self.assertIn(
            "'retrieve'",
            self.get_qs_block,
            "Condição deve incluir 'retrieve' para prefetch.",
        )

    def test_history_action_does_not_serialize_messages(self):
        """history usa LangchainService (Redis), não serializa conversation.messages."""
        history_block = _extract_block(self.viewset_block, r'def history\s*\(self.*request')
        self.assertNotIn(
            'messages',
            history_block,
            "history não deve acessar conversation.messages (usa apenas LangchainService).",
        )

    def test_clear_memory_action_does_not_serialize_messages(self):
        """clear_memory usa LangchainService (Redis), não serializa conversation.messages."""
        clear_block = _extract_block(self.viewset_block, r'def clear_memory\s*\(self.*request')
        self.assertNotIn(
            'messages',
            clear_block,
            "clear_memory não deve acessar conversation.messages (usa apenas LangchainService).",
        )

    def test_get_queryset_still_filters_by_accessible_agents(self):
        self.assertIn(
            '_accessible_agents',
            self.get_qs_block,
            "AgentConversationViewSet.get_queryset deve continuar escopando por agent acessível.",
        )

    def test_get_queryset_orders_by_last_message(self):
        self.assertIn(
            "order_by('-last_message_at')",
            self.get_qs_block,
            "AgentConversationViewSet.get_queryset deve manter order_by('-last_message_at').",
        )
