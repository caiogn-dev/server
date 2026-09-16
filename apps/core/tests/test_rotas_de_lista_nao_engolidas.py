"""Rota de lista registrada depois de `r''` era engolida pelo detalhe da primeira.

`router.register(r'', …)` gera `^(?P<pk>[^/.]+)/$`; registrado antes, ele casa
`preferences/`, `push/` e `conversations/` como se fossem um id. As rotas
filhas (`preferences/me/`, `push/register/`) funcionavam; só a lista não.
"""
from django.test import SimpleTestCase
from django.urls import resolve


class TestRotasDeListaNaoEngolidas(SimpleTestCase):

    def _view(self, url):
        return resolve(url).func.cls.__name__

    def test_preferencias_de_notificacao(self):
        # A viewset de preferências não tem `list`; a rota que existe é `me/`.
        self.assertEqual(self._view('/api/v1/notifications/preferences/me/'), 'NotificationPreferenceViewSet')

    def test_inscricoes_de_push(self):
        self.assertEqual(self._view('/api/v1/notifications/push/'), 'PushSubscriptionViewSet')

    def test_conversas_de_agente(self):
        self.assertEqual(self._view('/api/v1/agents/conversations/'), 'AgentConversationViewSet')

    def test_detalhe_da_raiz_continua_funcionando(self):
        self.assertEqual(self._view('/api/v1/notifications/abc123/'), 'NotificationViewSet')
        self.assertEqual(self._view('/api/v1/agents/abc123/'), 'AgentViewSet')
