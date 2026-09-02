"""Focus: 422 é validação genérica, não "ref duplicada".

A Focus devolve 422 para vários casos — certificado ausente, empresa não
habilitada, payload inválido — e o motivo real vem no corpo. Tratar todo 422
como ref repetida faz o código consultar uma nota que nunca existiu e devolver
o 404 da consulta ("Nota fiscal não encontrada") no lugar do erro verdadeiro.
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


class Focus422Tests(SimpleTestCase):
    def setUp(self):
        self.provider = FocusProvider(CFG)

    @patch('apps.fiscal.providers.focus.requests.get')
    @patch('apps.fiscal.providers.focus.requests.post')
    def test_422_de_certificado_mostra_o_motivo_real(self, mock_post, mock_get):
        mock_post.return_value = _resp(422, {
            'codigo': 'certificado_nao_cadastrado',
            'mensagem': 'Certificado digital não cadastrado para esta empresa',
        })
        result = self.provider.emit_nfce(ref='nfce-1', payload={})

        self.assertEqual(result.status, 'error')
        self.assertIn('Certificado digital', result.error_message)
        # nunca consulta: a nota não existe e o 404 mascararia o motivo
        mock_get.assert_not_called()

    @patch('apps.fiscal.providers.focus.requests.get')
    @patch('apps.fiscal.providers.focus.requests.post')
    def test_422_de_ref_duplicada_consulta_a_nota_existente(self, mock_post, mock_get):
        mock_post.return_value = _resp(422, {
            'codigo': 'nfe_referencia_duplicada',
            'mensagem': 'Já existe uma nota com esta referência',
        })
        mock_get.return_value = _resp(200, {
            'status': 'autorizado', 'chave_nfe': '1' * 44, 'numero': '9', 'serie': '1',
        })
        result = self.provider.emit_nfce(ref='nfce-1', payload={})

        self.assertEqual(result.status, 'authorized')
        self.assertEqual(result.chave_acesso, '1' * 44)
        mock_get.assert_called_once()

    @patch('apps.fiscal.providers.focus.requests.get')
    @patch('apps.fiscal.providers.focus.requests.post')
    def test_422_sem_codigo_conhecido_ainda_conta_o_que_veio(self, mock_post, mock_get):
        mock_post.return_value = _resp(422, {'mensagem': 'CNPJ do emitente inválido'})
        result = self.provider.emit_nfce(ref='nfce-1', payload={})

        self.assertEqual(result.status, 'error')
        self.assertIn('CNPJ do emitente', result.error_message)
        mock_get.assert_not_called()
