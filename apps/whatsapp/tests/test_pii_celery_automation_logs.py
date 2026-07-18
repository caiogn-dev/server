"""
Testes de contrato: telefones NÃO podem aparecer em claro nos logs de Celery/automation.

Cobre:
- apps/whatsapp/tasks/automation_tasks.py  (4 pontos: payment reminder, cart reminder,
  session cart reminder, re-engagement)
- apps/automation/services/automation_service.py  (3 pontos: _notify_customer,
  _send_auto_message START, _send_auto_message about-to-send)

Estratégia: varredura de código-fonte para garantir que as linhas de log em questão
não formam strings com o valor bruto de phone_number / customer_phone.
O padrão permitido é:  mask_phone(<expr>)  ou  %s  lazy (sem expor o telefone).
O padrão proibido é:   f"...{phone}..."  /  f"...{session.phone_number}..."  etc.
"""
import ast
import re
import textwrap
from pathlib import Path
from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[3]

# Padrões f-string proibidos — telefone diretamente interpolado sem mask_phone
_FORBIDDEN = re.compile(
    r'f["\']'                       # início de f-string
    r'.*?'                          # qualquer conteúdo
    r'\{[^}]*(?:phone|customer_phone|phone_number)[^}]*\}'   # {phone} / {session.phone_number}
    r'.*?["\']',                    # resto da f-string
    re.DOTALL,
)

# Padrão lazy-format proibido sem mask_phone:
#   logger.xxx("... %s ...", phone_number)       → o %s recebe o telefone em claro
# Detectado como: linha de logger + "%s" + vírgula + referência a variável de telefone
_LAZY_PHONE = re.compile(
    r'logger\.\w+\(["\'].*?%s.*?["\'].*?,.*?(?:phone_number|customer_phone|phone)\b',
    re.DOTALL,
)


def _source_of(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text()


def _logger_lines(source: str, pattern: re.Pattern) -> list[str]:
    """Retorna linhas do source que casam com o pattern."""
    return [
        line.strip()
        for line in source.splitlines()
        if pattern.search(line)
    ]


class AutomationTasksPIISourceTest(SimpleTestCase):
    """
    apps/whatsapp/tasks/automation_tasks.py:
    - Nenhuma f-string de logger deve interpolar phone_number/customer_phone em claro.
    - logger.info('... %s ...', phone_number) só é permitido se phone_number for a saída de mask_phone().
    """

    SOURCE_FILE = 'apps/whatsapp/tasks/automation_tasks.py'

    def setUp(self):
        self.src = _source_of(self.SOURCE_FILE)

    def test_sem_fstring_com_telefone_em_log(self):
        """Nenhuma f-string de logger deve expor telefone em claro."""
        lines = []
        for line in self.src.splitlines():
            stripped = line.strip()
            if not stripped.startswith('logger.'):
                continue
            if _FORBIDDEN.search(stripped):
                lines.append(stripped)

        self.assertEqual(
            lines, [],
            f"\nLinhas de log com telefone em claro em {self.SOURCE_FILE}:\n"
            + "\n".join(f"  {l}" for l in lines),
        )

    def test_mask_phone_importado(self):
        """mask_phone deve ser importado no módulo para uso nos logs."""
        self.assertIn(
            'mask_phone',
            self.src,
            f"mask_phone não encontrado em {self.SOURCE_FILE} — import ausente.",
        )

    def test_lazy_format_com_telefone_usa_mask(self):
        """
        Onde logger usa %s com variável de telefone, essa variável
        deve ser o resultado de mask_phone(), não o valor bruto.
        """
        suspect_lines = []
        for line in self.src.splitlines():
            stripped = line.strip()
            if not stripped.startswith('logger.'):
                continue
            # logger com %s referenciando phone sem mask_phone
            if re.search(r'%s.*?,.*?(?:phone_number|customer_phone)\b', stripped):
                if 'mask_phone' not in stripped:
                    suspect_lines.append(stripped)

        self.assertEqual(
            suspect_lines, [],
            f"\nLinhas de log com %s + telefone sem mask_phone em {self.SOURCE_FILE}:\n"
            + "\n".join(f"  {l}" for l in suspect_lines),
        )


class AutomationServicePIISourceTest(SimpleTestCase):
    """
    apps/automation/services/automation_service.py:
    - session.phone_number não pode aparecer em claro em f-strings de logger.
    """

    SOURCE_FILE = 'apps/automation/services/automation_service.py'

    def setUp(self):
        self.src = _source_of(self.SOURCE_FILE)

    def test_sem_fstring_com_session_phone_em_log(self):
        """Nenhuma f-string de logger deve expor session.phone_number em claro."""
        lines = []
        for line in self.src.splitlines():
            stripped = line.strip()
            if not stripped.startswith('logger.'):
                continue
            if re.search(r'f["\'].*\{.*session\.phone_number.*\}', stripped):
                lines.append(stripped)

        self.assertEqual(
            lines, [],
            f"\nLinhas de log com session.phone_number em claro em {self.SOURCE_FILE}:\n"
            + "\n".join(f"  {l}" for l in lines),
        )

    def test_mask_phone_importado(self):
        """mask_phone deve ser importado no módulo."""
        self.assertIn(
            'mask_phone',
            self.src,
            f"mask_phone não encontrado em {self.SOURCE_FILE} — import ausente.",
        )

    def test_sem_to_phone_number_em_log(self):
        """'to={session.phone_number}' em log deve ser mascarado."""
        for line in self.src.splitlines():
            stripped = line.strip()
            if not stripped.startswith('logger.'):
                continue
            if re.search(r'to=\{?session\.phone_number', stripped):
                self.fail(
                    f"Telefone em claro via 'to=' em log: {stripped}\n"
                    f"Arquivo: {self.SOURCE_FILE}",
                )
