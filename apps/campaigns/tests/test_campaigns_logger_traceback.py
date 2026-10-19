"""Regressão: ações de campanha não devem colocar traceback/str(exc) no campo message do log.

As actions start/pause/resume/cancel de CampaignViewSet tinham:
    logger.error(f"Campaign {pk} start error: {e}\\n{traceback.format_exc()}")

Isso coloca o traceback completo — que pode incluir URLs com access_token da API do
WhatsApp — diretamente no campo *message* do log record, que chega ao Sentry/CloudWatch
como texto livre sem possibilidade de scrubbing por campo.

O padrão correto é `logger.exception(...)` que registra o traceback em `exc_info`
(campo separado), onde redatores de campo do aggregator funcionam corretamente.

Todos SimpleTestCase — sem banco, sem rede.
Rodar:
  python3 -m unittest apps.campaigns.tests.test_campaigns_logger_traceback -v
"""
import pathlib
import re
import unittest


def _src():
    p = pathlib.Path(__file__).parent.parent / 'api' / 'views.py'
    return p.read_text()


class CampaignLoggerTracebackTest(unittest.TestCase):
    """CampaignViewSet actions não devem usar traceback.format_exc() em logger.error."""

    def test_start_nao_usa_traceback_no_logger_error(self):
        """start action: logger.error com traceback.format_exc() no message."""
        src = _src()
        matches = re.findall(r'logger\.error\(f["\'][^"\']*start[^"\']*traceback\.format_exc', src)
        self.assertEqual(matches, [], f"logger.error com traceback no start: {matches}")

    def test_pause_nao_usa_traceback_no_logger_error(self):
        """pause action: logger.error com traceback.format_exc() no message."""
        src = _src()
        matches = re.findall(r'logger\.error\(f["\'][^"\']*pause[^"\']*traceback\.format_exc', src)
        self.assertEqual(matches, [], f"logger.error com traceback no pause: {matches}")

    def test_resume_nao_usa_traceback_no_logger_error(self):
        """resume action: logger.error com traceback.format_exc() no message."""
        src = _src()
        matches = re.findall(r'logger\.error\(f["\'][^"\']*resume[^"\']*traceback\.format_exc', src)
        self.assertEqual(matches, [], f"logger.error com traceback no resume: {matches}")

    def test_cancel_nao_usa_traceback_no_logger_error(self):
        """cancel action: logger.error com traceback.format_exc() no message."""
        src = _src()
        matches = re.findall(r'logger\.error\(f["\'][^"\']*cancel[^"\']*traceback\.format_exc', src)
        self.assertEqual(matches, [], f"logger.error com traceback no cancel: {matches}")

    def test_nenhum_logger_error_usa_traceback_format_exc(self):
        """Nenhum logger.error deve ter traceback.format_exc() interpolado no message."""
        src = _src()
        matches = re.findall(r'logger\.error\(.*traceback\.format_exc', src)
        self.assertEqual(
            matches, [],
            f"logger.error com traceback.format_exc() no message: {matches}",
        )

    def test_nenhum_logger_error_interpola_exc_como_fstring(self):
        """Nenhum logger.error deve usar f-string com {e} nas actions de campanha."""
        src = _src()
        bad = [
            line.strip()
            for line in src.splitlines()
            if 'logger.error' in line and re.search(r'\{e\}', line)
            and re.search(r'(start|pause|resume|cancel)\s+error', line)
        ]
        self.assertEqual(bad, [], f"logger.error com {{e}} em f-string: {bad}")

    def test_traceback_import_removido_ou_nao_usado_em_logger(self):
        """traceback.format_exc() não deve aparecer em nenhuma chamada de logger."""
        src = _src()
        logger_lines_with_traceback = [
            line.strip()
            for line in src.splitlines()
            if 'logger.' in line and 'traceback.format_exc' in line
        ]
        self.assertEqual(
            logger_lines_with_traceback, [],
            f"logger com traceback.format_exc(): {logger_lines_with_traceback}",
        )
