"""O detalhamento de campo da Focus precisa chegar na tela.

"Erro na validação do Schema XML, verifique o detalhamento dos erros" sozinho
não diz o que corrigir — o detalhamento vem em `erros` e era descartado.
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.fiscal.providers.focus import FocusProvider

CFG = {'provider': 'focus', 'ambiente': 'homologacao', 'focus_token': 'tok'}


def _resp(status_code, payload):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = b'{}'
    resp.json.return_value = payload
    return resp


class DetalheDeErroTests(SimpleTestCase):
    def setUp(self):
        self.provider = FocusProvider(CFG)

    @patch('apps.fiscal.providers.focus.requests.get')
    @patch('apps.fiscal.providers.focus.requests.post')
    def test_campos_reprovados_entram_na_mensagem(self, mock_post, mock_get):
        mock_post.return_value = _resp(422, {
            'codigo': 'erro_validacao_schema',
            'mensagem': 'Erro na validação do Schema XML, verifique o detalhamento dos erros',
            'erros': [
                {'campo': 'presenca_comprador', 'mensagem': 'campo obrigatório ausente'},
                {'campo': 'cep_emitente', 'mensagem': 'formato inválido'},
            ],
        })
        result = self.provider.emit_nfce(ref='nfce-1', payload={})

        self.assertEqual(result.status, 'error')
        self.assertIn('presenca_comprador', result.error_message)
        self.assertIn('campo obrigatório ausente', result.error_message)
        self.assertIn('cep_emitente', result.error_message)
        mock_get.assert_not_called()

    @patch('apps.fiscal.providers.focus.requests.post')
    def test_sem_detalhamento_mantem_so_a_mensagem(self, mock_post):
        mock_post.return_value = _resp(422, {'mensagem': 'CNPJ do emitente inválido'})
        result = self.provider.emit_nfce(ref='nfce-1', payload={})
        self.assertEqual(result.error_message, 'CNPJ do emitente inválido')

    @patch('apps.fiscal.providers.focus.requests.post')
    def test_erro_de_autorizacao_da_sefaz_tambem_detalha(self, mock_post):
        mock_post.return_value = _resp(200, {
            'status': 'erro_autorizacao',
            'mensagem_sefaz': 'Rejeicao: CFOP invalido',
            'erros': [{'campo': 'cfop', 'mensagem': 'valor 5102 nao permitido'}],
        })
        result = self.provider.emit_nfce(ref='nfce-1', payload={})
        self.assertEqual(result.status, 'rejected')
        self.assertIn('Rejeicao: CFOP invalido', result.error_message)
        self.assertIn('cfop', result.error_message)
