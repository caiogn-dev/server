"""Regressão de segurança: emit_nfce não deve expor str(exc) nas respostas HTTP.

Dois vetores cobertos:

1. SefazProvider.emit_nfce() lança FiscalNotConfigured com mensagem que contém
   o caminho de arquivo interno 'apps/fiscal/providers/sefaz.py'.
   Esse str(exc) é devolvido diretamente na resposta HTTP via
   emit_nfce view → Response({'error': str(exc)}).
   Um atacante autenticado obtém estrutura interna do projeto.

2. emit_nfce_for_order() captura Exception genérica (erros de rede, timeout)
   e armazena str(exc) em FiscalDocument.error_message, que é então retornado
   na resposta HTTP. Uma exceção requests.ConnectionError revela:
   - URL interna da Focus API (host/port)
   - Parâmetros de query com o UUID do pedido

3. services.py eleva FiscalNotConfigured com a string
   'store.metadata["fiscal"]' que vaza a estrutura interna de metadados
   do modelo Store para qualquer usuário que acione o endpoint.

Todos SimpleTestCase — sem Docker/PostgreSQL.
Rodar:
  DJANGO_SETTINGS_MODULE=config.settings.test_serializer \\
  python manage.py test apps.fiscal.tests.test_nfce_str_exc_disclosure -v 2
"""
import inspect
from unittest.mock import MagicMock, patch, call

from django.test import SimpleTestCase

from apps.fiscal.providers.base import FiscalNotConfigured
from apps.fiscal.providers.sefaz import SefazProvider
from apps.fiscal import services as fiscal_services


class SefazProviderMensagemSemArquivoInternoTest(SimpleTestCase):
    """SefazProvider.emit_nfce não deve revelar caminhos de arquivo interno."""

    def _get_exception_message(self):
        provider = SefazProvider({})
        with self.assertRaises(FiscalNotConfigured) as ctx:
            provider.emit_nfce(ref='qualquer-ref', payload={})
        return str(ctx.exception)

    def test_mensagem_nao_contem_caminho_apps_fiscal(self):
        """'apps/fiscal' não deve aparecer na mensagem de erro ao usuário."""
        msg = self._get_exception_message()
        self.assertNotIn('apps/fiscal', msg)

    def test_mensagem_nao_contem_nome_de_arquivo_py(self):
        """O nome do arquivo providers/sefaz.py não deve aparecer na mensagem."""
        msg = self._get_exception_message()
        self.assertNotIn('providers/sefaz.py', msg)

    def test_mensagem_ainda_menciona_certificado_a1(self):
        """A mensagem ainda deve orientar o operador sobre o pré-requisito."""
        msg = self._get_exception_message()
        self.assertIn('certificado A1', msg)


class ServicesMetadataKeyLeakTest(SimpleTestCase):
    """emit_nfce_for_order não deve revelar 'store.metadata["fiscal"]' no erro."""

    def test_mensagem_sem_config_nao_contem_metadata_key(self):
        """Análise estática: a string 'store.metadata["fiscal"]' não deve estar
        no código de emit_nfce_for_order (iria parar na resposta HTTP via str(exc))."""
        src = inspect.getsource(fiscal_services.emit_nfce_for_order)
        self.assertNotIn(
            'store.metadata["fiscal"]',
            src,
            'A string store.metadata["fiscal"] vaza estrutura interna na resposta HTTP',
        )

    def test_services_nao_usa_str_exc_em_error_message(self):
        """Análise estática: o bloco 'except Exception as exc' em emit_nfce_for_order
        não deve usar str(exc) diretamente como doc.error_message."""
        src = inspect.getsource(fiscal_services.emit_nfce_for_order)
        # A atribuição problemática era: doc.error_message = str(exc)
        # Após o fix, o bloco deve usar uma mensagem genérica
        self.assertNotIn(
            'str(exc)',
            src,
            'str(exc) ainda é usado em doc.error_message — vaza erros internos de rede',
        )


class EmitNfceNetworkErrorMessageGenericaTest(SimpleTestCase):
    """Comportamento: falha de rede grava mensagem genérica em doc.error_message."""

    def test_connection_error_usa_mensagem_generica(self):
        """Se o provider lança requests.ConnectionError, doc.error_message deve ser
        uma mensagem genérica, não str(exc) com detalhes da URL interna."""
        import requests as req_lib

        # Simula a string que requests.ConnectionError geraria — contém URL interna
        internal_error_str = (
            "HTTPSConnectionPool(host='api.focusnfe.com.br', port=443): "
            "Max retries exceeded with url: /v2/nfce?ref=nfce-some-uuid"
        )

        mock_doc = MagicMock()
        mock_doc.ref = 'nfce-test-ref'
        mock_doc.status = 'pending'
        mock_doc.error_message = ''

        mock_existing_qs = MagicMock()
        mock_existing_qs.first.return_value = None  # sem documento existente

        with (
            patch.object(fiscal_services.FiscalDocument.objects, 'filter',
                         return_value=mock_existing_qs),
            patch.object(fiscal_services.FiscalDocument.objects, 'create',
                         return_value=mock_doc),
            patch('apps.fiscal.services.get_fiscal_config',
                  return_value={'provider': 'focus', 'cnpj': '12345678000190', 'focus_token': 'tok'}),
            patch('apps.fiscal.services.build_nfce_payload', return_value={}),
            patch('apps.fiscal.providers.focus.FocusProvider.emit_nfce',
                  side_effect=req_lib.exceptions.ConnectionError(internal_error_str)),
        ):
            mock_order = MagicMock()
            mock_order.id = 'order-test-id'
            mock_order.store = MagicMock()
            mock_order.store.metadata = {'fiscal': {'provider': 'focus', 'focus_token': 'tok'}}

            result = fiscal_services.emit_nfce_for_order(mock_order)

        saved_message = mock_doc.error_message
        self.assertNotIn('HTTPSConnectionPool', saved_message,
                         'URL interna Focus API não deve aparecer no error_message retornado')
        self.assertNotIn('api.focusnfe.com.br', saved_message,
                         'Hostname Focus API não deve aparecer no error_message retornado')
        # A mensagem deve ser genérica mas descritiva para o operador
        self.assertTrue(
            len(saved_message) > 0,
            'error_message não pode ser vazio — precisa de uma mensagem genérica',
        )
