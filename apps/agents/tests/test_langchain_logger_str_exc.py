"""
Testa que nenhum handler `except Exception` em langchain_service.py
interpola str(e) no campo message de logger.error / logger.warning.

Vetor real: exceções do OpenAI/Anthropic/Kimi incluem o texto completo
da resposta HTTP de erro — que frequentemente contém o token de API no
campo `message` do JSON de erro. Com f-string + logger.error, esse token
vai para o campo `message` do LogRecord e é indexado pelo Sentry/GlitchTip
como texto livre pesquisável.

logger.exception() coloca o traceback em `exc_info` (campo separado),
onde redatores de campo do aggregator funcionam. O campo `message` fica
genérico.

Todos estes testes são SimpleTestCase — sem banco, sem rede, sem Docker.
"""
import os
import re
import unittest

_SERVICE_PATH = os.path.join(
    os.path.dirname(__file__),
    '..', 'services', 'langchain_service.py',
)


def _source() -> str:
    with open(_SERVICE_PATH, encoding='utf-8') as f:
        return f.read()


class LangchainLoggerStrExcTest(unittest.TestCase):
    """Verifica que str(e) / {e} não aparece em chamadas de logger.error."""

    def test_sem_logger_error_com_fstring_e(self):
        """Nenhum logger.error(f"...{e}") deve existir no módulo."""
        src = _source()
        matches = re.findall(r'logger\.error\(f["\'].*\{e\}', src)
        self.assertEqual(
            matches, [],
            f"logger.error com {{e}} encontrado: {matches}",
        )

    def test_sem_logger_error_com_str_e(self):
        """Nenhum logger.error(f"...{str(e)}") deve existir no módulo."""
        src = _source()
        matches = re.findall(r'logger\.error\(f["\'].*str\(e\)', src)
        self.assertEqual(
            matches, [],
            f"logger.error com str(e) encontrado: {matches}",
        )

    def test_base_api_exception_sem_str_e(self):
        """BaseAPIException em process_message não deve interpolar str(e)."""
        src = _source()
        matches = re.findall(r'raise BaseAPIException\(f["\'].*str\(e\)', src)
        self.assertEqual(
            matches, [],
            f"BaseAPIException com str(e) encontrado: {matches}",
        )

    def test_process_message_stream_yield_sem_str_e(self):
        """O yield de erro em process_message_stream não expõe str(e)."""
        src = _source()
        matches = re.findall(r"['\"]error['\"]\s*:\s*str\(e\)", src)
        self.assertEqual(
            matches, [],
            f"str(e) em yield de erro encontrado: {matches}",
        )

    def test_get_memory_nao_usa_logger_error_com_str_exc(self):
        """_get_memory não usa logger.error com {e} interpolado."""
        src = _source()
        self.assertNotIn(
            'logger.error(f"Error creating memory: {e}")',
            src,
            "logger.error com {e} ainda presente em _get_memory",
        )

    def test_process_message_nao_usa_logger_error_com_str_exc(self):
        """process_message não usa logger.error com {e} interpolado."""
        src = _source()
        self.assertNotIn(
            'logger.error(f"Error processing message: {e}")',
            src,
            "logger.error com {e} ainda presente em process_message",
        )

    def test_contagem_logger_exception_no_minimo_14(self):
        """Deve haver pelo menos 14 usos de logger.exception no módulo (um por fix)."""
        src = _source()
        count = len(re.findall(r'logger\.exception\(', src))
        self.assertGreaterEqual(
            count, 14,
            f"Esperado ≥ 14 logger.exception, encontrado {count}",
        )


if __name__ == '__main__':
    unittest.main()
