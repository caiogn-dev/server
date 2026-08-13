"""Regressão de segurança: connect() e send_message() não devem expor str(exc)
nas respostas HTTP do Instagram.

Dois vetores cobertos:

1. InstagramAccountViewSet.connect() (POST /instagram/accounts/connect/)
   A troca de code OAuth falhava com requests.HTTPError. O handler capturava
   exc.response.text (corpo bruto da resposta da API do Instagram) OU str(exc),
   retornando ambos via HTTP 400 para o cliente autenticado.
   Resposta da Meta API pode conter: mensagens de erro internas, fbtrace_ids,
   e detalhes sobre a validade/expiração de tokens.

2. InstagramConversationViewSet.send_message() (POST /instagram/conversations/{pk}/send_message/)
   Qualquer exceção no serviço de envio retornava str(exc) direto na resposta
   HTTP 400. InstagramAPIException e outros erros do serviço podem conter
   endpoint URLs, IDs internos ou mensagens detalhadas da Graph API.

Estratégia: testes de análise estática leem o arquivo-fonte diretamente (sem
importar Django/models), garantindo que os padrões inseguros não estejam presentes.
Os testes de integração (mock) requerem ambiente Django completo.
"""
import os
import re
import unittest

# Caminho absoluto para o arquivo de views do Instagram
_VIEWS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "api", "views.py"
)


def _read_views_source():
    with open(_VIEWS_PATH, encoding="utf-8") as f:
        return f.read()


def _extract_method_source(full_source, method_name):
    """Extrai o corpo de um método pelo nome usando indentação como delimitador."""
    lines = full_source.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.search(rf"def {re.escape(method_name)}\s*\(", line):
            start = i
            break
    if start is None:
        raise ValueError(f"Método {method_name!r} não encontrado em {_VIEWS_PATH}")

    # Detecta indentação do def
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    result = [lines[start]]
    for line in lines[start + 1:]:
        stripped = line.lstrip()
        if not stripped:
            result.append(line)
            continue
        indent = len(line) - len(stripped)
        if indent <= base_indent and stripped:
            break
        result.append(line)
    return "\n".join(result)


class ConnectHandlerNoRawTextTest(unittest.TestCase):
    """connect() não deve incluir raw.text ou str(exc) na resposta HTTP."""

    @classmethod
    def setUpClass(cls):
        cls._src = _extract_method_source(_read_views_source(), "connect")

    def test_raw_text_not_in_response(self):
        self.assertNotIn(
            "raw.text",
            self._src,
            "connect() não deve expor exc.response.text (corpo bruto da Meta API) na resposta.",
        )

    def test_str_exc_not_in_response(self):
        lines_with_str_exc = [
            line for line in self._src.splitlines()
            if "str(exc)" in line and "Response" in line
        ]
        self.assertEqual(
            lines_with_str_exc,
            [],
            f"connect() não deve passar str(exc) para Response(): {lines_with_str_exc}",
        )

    def test_detail_variable_not_in_response(self):
        """A variável `detail` continha raw.text — não deve aparecer em Response."""
        lines_with_detail_response = [
            line for line in self._src.splitlines()
            if "detail" in line and "Response" in line and "error" in line
        ]
        self.assertEqual(
            lines_with_detail_response,
            [],
            f"connect() não deve incluir variável `detail` (raw.text) em Response(): {lines_with_detail_response}",
        )

    def test_connect_generic_message_present(self):
        """Garante que a mensagem genérica em português está no handler de erro."""
        self.assertIn(
            "Falha ao trocar",
            self._src,
            "connect() deve conter mensagem genérica 'Falha ao trocar' no handler de erro.",
        )


class SendMessageHandlerNoStrExcTest(unittest.TestCase):
    """send_message() não deve expor str(exc) na resposta HTTP."""

    @classmethod
    def setUpClass(cls):
        cls._src = _extract_method_source(_read_views_source(), "send_message")
        cls._full_src = _read_views_source()

    def test_str_exc_not_in_response(self):
        lines_with_str_exc = [
            line for line in self._src.splitlines()
            if "str(exc)" in line and "Response" in line
        ]
        self.assertEqual(
            lines_with_str_exc,
            [],
            f"send_message() não deve passar str(exc) para Response(): {lines_with_str_exc}",
        )

    def test_generic_message_present(self):
        """Garante que a mensagem genérica em português está no handler de erro."""
        self.assertIn(
            "Falha ao enviar",
            self._src,
            "send_message() deve conter mensagem genérica 'Falha ao enviar' no handler de erro.",
        )

    def test_generic_message_does_not_contain_exception_details(self):
        """Verifica estaticamente que a resposta de erro usa texto fixo sem exc."""
        response_lines = [
            line.strip() for line in self._src.splitlines()
            if "Response" in line and "error" in line and "400" in line
        ]
        for line in response_lines:
            self.assertNotIn(
                "exc",
                line,
                f"Linha de resposta de erro não deve referenciar a variável exc: {line}",
            )

    def test_media_url_validation_in_view(self):
        """Valida que a view verifica media_url antes de chamar o serviço."""
        self.assertIn(
            "media_url",
            self._src,
            "send_message() deve validar media_url para tipos IMAGE/VIDEO/AUDIO.",
        )
        self.assertIn(
            "IMAGE",
            self._src,
            "send_message() deve checar tipos de mídia (IMAGE/VIDEO/AUDIO) antes do serviço.",
        )
        lines_with_media_validation = [
            line for line in self._src.splitlines()
            if "media_url" in line and ("IMAGE" in line or "AUDIO" in line or "VIDEO" in line)
        ]
        self.assertGreater(
            len(lines_with_media_validation),
            0,
            "send_message() deve conter validação de media_url para tipos de mídia.",
        )


if __name__ == "__main__":
    unittest.main()
