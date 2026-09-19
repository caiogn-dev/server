"""
Testes de regressão: str(e) de exceção do Resend não deve vazar em respostas HTTP.

P1 — info-disclosure: ResendAPIError e outros podem incluir detalhes internos
(credenciais, rate-limit, URLs de API interna) na mensagem de exceção.

Estratégia: análise estática (sem DB/Docker) — garante que os padrões proibidos
não existem no fonte, de forma análoga à suíte de segurança de julho/2026.
"""
import os
import re
import unittest


def _read(relative_path: str) -> str:
    base = os.path.join(os.path.dirname(__file__), '..', '..', '..')
    full = os.path.realpath(os.path.join(base, relative_path))
    with open(full, encoding='utf-8') as f:
        return f.read()


class EmailMarketingServiceStrExcTest(unittest.TestCase):
    """send_single_email() não deve retornar str(e) em dict de erro."""

    def setUp(self):
        self.src = _read('apps/marketing/services/email_marketing_service.py')

    def _func_body(self, func_name: str) -> str:
        match = re.search(
            rf'def {func_name}\b.*?(?=\n    def |\nclass |\Z)',
            self.src,
            re.DOTALL,
        )
        return match.group(0) if match else ''

    def test_send_single_email_sem_str_e_em_return(self):
        """send_single_email não deve ter 'error': str(e) em nenhum return."""
        body = self._func_body('send_single_email')
        self.assertNotIn("'error': str(e)", body,
                         "send_single_email retorna str(e) — info-disclosure ao cliente")
        self.assertNotIn('"error": str(e)', body,
                         "send_single_email retorna str(e) — info-disclosure ao cliente")

    def test_send_single_email_excecao_nao_vaza_detalhes(self):
        """except Exception em send_single_email não expõe str(e) na resposta."""
        body = self._func_body('send_single_email')
        # Acha blocos except Exception (genérico, não ValueError/DoesNotExist)
        bloco_match = re.search(r'except Exception.*?(?=\n    [^\s]|\Z)', body, re.DOTALL)
        if bloco_match:
            bloco = bloco_match.group(0)
            # Dentro do bloco de captura genérica, não pode haver return com str(e)
            self.assertNotIn("str(e)", bloco.split('return', 1)[-1] if 'return' in bloco else '',
                             "str(e) exposto na resposta de except Exception")


class EmailAutomationServiceStrExcTest(unittest.TestCase):
    """EmailAutomationService.trigger() não deve retornar str(e) em dict de erro."""

    def setUp(self):
        self.src = _read('apps/marketing/services/email_automation_service.py')

    def test_trigger_sem_str_e_em_return(self):
        """trigger() não deve ter 'error': str(e) em nenhum return."""
        # Busca todos os blocos except genérico do arquivo
        blocos = re.findall(
            r'except Exception as e:(.*?)(?=\n\s{0,8}except|\n\s{0,4}def |\Z)',
            self.src,
            re.DOTALL,
        )
        for bloco in blocos:
            if 'return' in bloco:
                after_return = bloco.split('return', 1)[-1]
                self.assertNotIn("str(e)", after_return,
                                 "except Exception retorna str(e) — info-disclosure ao cliente")

    def test_trigger_sem_error_str_e_literal(self):
        """Padrão literal 'error': str(e) ausente em return de except."""
        # Extrai somente o método trigger/send principal
        match = re.search(
            r'def (trigger|send)\b.*?(?=\n    def |\nclass |\Z)',
            self.src,
            re.DOTALL,
        )
        if match:
            body = match.group(0)
            self.assertNotIn("'error': str(e)", body,
                             "except em trigger/send expõe str(e) — info-disclosure")
            self.assertNotIn('"error": str(e)', body,
                             "except em trigger/send expõe str(e) — info-disclosure")


class MarketingViewStrExcTest(unittest.TestCase):
    """EmailCampaignViewSet.send não expõe str(e) via except Exception."""

    def setUp(self):
        self.src = _read('apps/marketing/api/views.py')

    def _action_send_body(self) -> str:
        match = re.search(
            r'def send\(self.*?(?=\n    def |\n\nclass |\Z)',
            self.src,
            re.DOTALL,
        )
        return match.group(0) if match else ''

    def test_action_send_sem_str_e_em_except(self):
        """Action 'send' de EmailCampaignViewSet não deve retornar str(e) no except."""
        body = self._action_send_body()
        # Localiza todos os except genéricos dentro da action
        blocos = re.findall(
            r'except Exception.*?(?=\n        def |\n    def |\Z)',
            body,
            re.DOTALL,
        )
        for bloco in blocos:
            self.assertNotIn("'error': str(e)", bloco,
                             "Action send: except Exception expõe str(e) — info-disclosure")

    def test_action_send_nao_tem_str_e_literal(self):
        """Padrão literal str(e) ausente na action send."""
        body = self._action_send_body()
        self.assertNotIn("'error': str(e)", body,
                         "Action send: str(e) exposto ao cliente via Response")


if __name__ == '__main__':
    unittest.main(verbosity=2)
