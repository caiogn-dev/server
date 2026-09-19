"""
Testes de regressão: exceção do Resend não deve vazar em respostas HTTP.

P1 — info-disclosure: ResendAPIError e outros podem incluir detalhes internos
(credenciais, rate-limit, URLs de API interna) na mensagem de exceção.

Estratégia: análise estática (sem DB/Docker) — verifica que nenhum str(<var>)
de except genérico aparece em returns/Responses, independente do nome da variável
(str(e), str(exc), str(err), str(error), …).
"""
import os
import re
import unittest


def _read(relative_path: str) -> str:
    base = os.path.join(os.path.dirname(__file__), '..', '..', '..')
    full = os.path.realpath(os.path.join(base, relative_path))
    with open(full, encoding='utf-8') as f:
        return f.read()


# Captura: except Exception as <var>: <corpo>
# Grupo 1 = nome da variável, Grupo 2 = corpo do bloco até próximo nível
_EXCEPT_GENERIC_RE = re.compile(
    r'except\s+Exception\s+as\s+(\w+)\s*:(.*?)'
    r'(?=\n\s{0,8}except|\n\s{0,4}def |\n\s{0,0}class |\Z)',
    re.DOTALL,
)


def _str_exc_in_returns(src: str) -> list:
    """
    Retorna [(varname, trecho)] onde str(<varname>) aparece em algum return
    dentro de um except Exception genérico, independente do nome da variável.
    """
    problemas = []
    for m in _EXCEPT_GENERIC_RE.finditer(src):
        varname = m.group(1)
        body = m.group(2)
        for ret_m in re.finditer(
            r'return\b(.*?)(?=\n\s*(?:return\b|raise\b|\w)|\Z)', body, re.DOTALL
        ):
            ret_text = ret_m.group(1)
            if re.search(rf'\bstr\s*\(\s*{re.escape(varname)}\s*\)', ret_text):
                problemas.append((varname, ret_text.strip()))
    return problemas


class EmailMarketingServiceStrExcTest(unittest.TestCase):
    """send_single_email() não deve retornar str(<exc>) em dict de erro."""

    def setUp(self):
        self.src = _read('apps/marketing/services/email_marketing_service.py')

    def _func_body(self, func_name: str) -> str:
        match = re.search(
            rf'def {func_name}\b.*?(?=\n    def |\nclass |\Z)',
            self.src,
            re.DOTALL,
        )
        return match.group(0) if match else ''

    def test_send_single_email_sem_str_exc_em_return(self):
        """send_single_email: str(<var>) de except genérico não pode aparecer em return."""
        body = self._func_body('send_single_email')
        problemas = _str_exc_in_returns(body)
        self.assertEqual(
            [], problemas,
            f"send_single_email retorna str(exc) — info-disclosure: {problemas}",
        )

    def test_send_single_email_excecao_nao_vaza_detalhes(self):
        """except Exception em send_single_email não expõe str(<var>) na resposta."""
        body = self._func_body('send_single_email')
        problemas = _str_exc_in_returns(body)
        self.assertFalse(
            problemas,
            f"str(<exc>) exposto na resposta de except Exception: {problemas}",
        )


class EmailAutomationServiceStrExcTest(unittest.TestCase):
    """EmailAutomationService não deve retornar str(<exc>) em dict de erro."""

    def setUp(self):
        self.src = _read('apps/marketing/services/email_automation_service.py')

    def test_arquivo_sem_str_exc_em_return(self):
        """Arquivo inteiro: str(<var>) de except genérico não pode aparecer em return."""
        problemas = _str_exc_in_returns(self.src)
        self.assertEqual(
            [], problemas,
            f"except Exception retorna str(exc) — info-disclosure: {problemas}",
        )

    def test_trigger_send_sem_error_str_exc(self):
        """Métodos trigger/send: sem 'error': str(<var>) em nenhum return."""
        match = re.search(
            r'def (trigger|send)\b.*?(?=\n    def |\nclass |\Z)',
            self.src,
            re.DOTALL,
        )
        if match:
            body = match.group(0)
            problemas = _str_exc_in_returns(body)
            self.assertEqual(
                [], problemas,
                f"except em trigger/send expõe str(exc) — info-disclosure: {problemas}",
            )


class MarketingViewStrExcTest(unittest.TestCase):
    """EmailCampaignViewSet.send não expõe str(<exc>) via except Exception."""

    def setUp(self):
        self.src = _read('apps/marketing/api/views.py')

    def _action_send_body(self) -> str:
        match = re.search(
            r'def send\(self.*?(?=\n    def |\n\nclass |\Z)',
            self.src,
            re.DOTALL,
        )
        return match.group(0) if match else ''

    def test_action_send_sem_str_exc_em_except(self):
        """Action 'send': str(<var>) de except genérico não pode aparecer em return/Response."""
        body = self._action_send_body()
        problemas = _str_exc_in_returns(body)
        self.assertEqual(
            [], problemas,
            f"Action send: except Exception expõe str(exc) — info-disclosure: {problemas}",
        )

    def test_action_send_nao_tem_str_exc_literal(self):
        """Action 'send': sem nenhum str(<var>) em returns de excepts genéricos."""
        body = self._action_send_body()
        problemas = _str_exc_in_returns(body)
        self.assertFalse(
            problemas,
            f"Action send: str(exc) exposto ao cliente via Response: {problemas}",
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
