"""Erro no navegador do operador precisa chegar em alguém.

MEDIDO (05/10): o GlitchTip só tem o projeto `server2`. O painel tem error
boundary, mas o erro ia para o `console.error` do computador da loja — tela
quebrada no meio do almoço e ninguém do outro lado sabe.

O painel manda o erro para cá; daqui ele vira `logger.error`, que a integração
do Sentry já transforma em issue no GlitchTip. Mensagem já formatada (sem
parâmetros) para cada erro distinto virar uma issue própria, e a rota sem ids
para o mesmo erro em pedidos diferentes não virar cem issues.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

URL = '/api/v1/core/erros-do-painel/'


class ErrosDoPainelTest(APITestCase):
    def setUp(self):
        cache.clear()

    def _post(self, **dados):
        corpo = {
            'mensagem': "Cannot read properties of undefined (reading 'map')",
            'rota': '/pedidos/7f0c1d2e-1111-2222-3333-444455556666',
            'origem': 'render',
            'pilha': 'at OrdersPage (index-abc.js:1:2)',
            'versao': 'index-CTXftp9R',
            **dados,
        }
        return self.client.post(URL, corpo, format='json')

    def test_vira_logger_error_com_rota_sem_id(self):
        with self.assertLogs('apps.core.erros_do_painel', level='ERROR') as logs:
            resp = self._post()
        self.assertEqual(resp.status_code, 204)
        linha = logs.output[0]
        self.assertIn("[painel] Cannot read properties of undefined (reading 'map')", linha)
        self.assertIn('/pedidos/:id', linha)
        self.assertNotIn('7f0c1d2e', linha)

    def test_aceita_sem_login(self):
        """Erro na tela de login também conta."""
        with self.assertLogs('apps.core.erros_do_painel', level='ERROR'):
            resp = self._post(rota='/login')
        self.assertEqual(resp.status_code, 204)

    def test_usuario_logado_vai_junto(self):
        user = get_user_model().objects.create_user('operador', 'o@t.com', 'x')
        self.client.force_authenticate(user)
        with self.assertLogs('apps.core.erros_do_painel', level='ERROR') as logs:
            self._post()
        self.assertEqual(logs.records[0].usuario, user.id)

    def test_sem_mensagem_responde_400(self):
        resp = self._post(mensagem='  ')
        self.assertEqual(resp.status_code, 400)

    def test_texto_gigante_e_cortado(self):
        with self.assertLogs('apps.core.erros_do_painel', level='ERROR') as logs:
            self._post(mensagem='x' * 5000, pilha='y' * 50000)
        self.assertLess(len(logs.output[0]), 6000)

    def test_enxurrada_do_mesmo_ip_e_barrada(self):
        respostas = []
        with self.assertLogs('apps.core.erros_do_painel', level='ERROR'):
            for _ in range(40):
                respostas.append(self._post().status_code)
        self.assertIn(429, respostas)
