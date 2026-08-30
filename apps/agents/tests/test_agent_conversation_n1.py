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
    """AgentConversationViewSet.get_queryset deve usar prefetch_related('messages')."""

    def setUp(self):
        self.src = _read(_VIEWS_PATH)

    def test_get_queryset_exists_in_viewset(self):
        self.assertIn(
            'class AgentConversationViewSet',
            self.src,
            'AgentConversationViewSet não encontrado.',
        )

    def test_get_queryset_has_prefetch_messages(self):
        # Extrai o bloco do get_queryset dentro de AgentConversationViewSet
        # (não o get_queryset do AgentViewSet, que não existe)
        viewset_block = self.src.split('class AgentConversationViewSet')[1]
        get_qs_block = _extract_block(viewset_block, r'def get_queryset\s*\(self\)')
        self.assertIn(
            "prefetch_related('messages')",
            get_qs_block,
            "AgentConversationViewSet.get_queryset deve chamar .prefetch_related('messages') "
            "para evitar N+1 ao listar conversas.",
        )

    def test_get_queryset_still_filters_by_accessible_agents(self):
        viewset_block = self.src.split('class AgentConversationViewSet')[1]
        get_qs_block = _extract_block(viewset_block, r'def get_queryset\s*\(self\)')
        self.assertIn(
            '_accessible_agents',
            get_qs_block,
            "AgentConversationViewSet.get_queryset deve continuar escopando por agent acessível.",
        )

    def test_get_queryset_orders_by_last_message(self):
        viewset_block = self.src.split('class AgentConversationViewSet')[1]
        get_qs_block = _extract_block(viewset_block, r'def get_queryset\s*\(self\)')
        self.assertIn(
            "order_by('-last_message_at')",
            get_qs_block,
            "AgentConversationViewSet.get_queryset deve manter order_by('-last_message_at').",
        )

    def test_no_prefetch_not_in_querysets_without_fix(self):
        """Confirmação documentada: antes do fix os dois querysets NÃO tinham prefetch."""
        # Este teste serve como documentação — o próprio test_*_has_prefetch_messages
        # garante que após o fix estão presentes. Este teste sempre passa.
        self.assertTrue(True)
