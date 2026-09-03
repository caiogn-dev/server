"""
Testes estáticos: garantem que números de telefone brutos não aparecem
em chamadas de logger dentro de fusao_de_conversas.py e message_service.py.

LGPD art. 46 — medidas técnicas de segurança para dados pessoais.
"""
import ast
import re
import os
from unittest import TestCase


def _source(relative_path):
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return open(os.path.join(base, relative_path)).read()


class FusaoDeConversasPiiTest(TestCase):
    """Verifica que fusao_de_conversas.py não loga telefones brutos."""

    def setUp(self):
        self.source = _source('apps/whatsapp/services/fusao_de_conversas.py')

    def test_mask_phone_importado(self):
        self.assertIn('from apps.core.pii import mask_phone', self.source)

    def test_sem_phone_number_bruto_em_logger(self):
        """Nenhuma chamada de logger deve conter phone_number sem mask_phone."""
        for line in self.source.splitlines():
            if 'logger.' in line and 'phone_number' in line:
                self.assertIn('mask_phone', line, (
                    f"Telefone bruto em log: {line.strip()}"
                ))

    def test_sem_absorvidas_bruto_em_logger(self):
        """item['absorvidas'] não pode ser passado diretamente (sem len/count) a um logger."""
        for line in self.source.splitlines():
            if 'logger.' not in line:
                continue
            if "item['absorvidas']" not in line:
                continue
            # Passa se a lista está dentro de len() — só o tamanho vai para o log
            if re.search(r"len\(\s*item\['absorvidas'\]\s*\)", line):
                continue
            self.fail(f"Lista de telefones bruta em log: {line.strip()}")

    def test_canonica_phone_number_mascarado(self):
        """canonica.phone_number em logger deve estar dentro de mask_phone()."""
        for line in self.source.splitlines():
            if 'logger.' in line and 'canonica.phone_number' in line:
                self.assertIn('mask_phone', line, (
                    f"canonica.phone_number sem máscara: {line.strip()}"
                ))

    def test_origem_phone_number_mascarado(self):
        """origem.phone_number em logger deve estar dentro de mask_phone()."""
        for line in self.source.splitlines():
            if 'logger.' in line and 'origem.phone_number' in line:
                self.assertIn('mask_phone', line, (
                    f"origem.phone_number sem máscara: {line.strip()}"
                ))


class MessageServicePiiTest(TestCase):
    """Verifica que message_service.py não loga telefones brutos."""

    def setUp(self):
        self.source = _source('apps/whatsapp/services/message_service.py')

    def test_mask_phone_importado(self):
        self.assertIn('from apps.core.pii import mask_phone', self.source)

    def test_sem_phone_number_bruto_em_fstring_logger(self):
        """f-strings em logger não devem conter {phone_number} sem máscara."""
        fstring_pattern = re.compile(r'logger\.\w+\(f"[^"]*\{phone_number\}[^"]*"\)')
        matches = fstring_pattern.findall(self.source)
        self.assertEqual(
            matches, [],
            f"Telefone bruto em f-string de logger: {matches}",
        )

    def test_sem_phone_number_bruto_em_formato_logger(self):
        """Chamadas de logger não devem logar phone_number (de pessoa) sem mask_phone.

        `phone_number_id` é o ID da API da Meta (não é dado pessoal) e está
        excluído desta verificação.
        """
        for line in self.source.splitlines():
            if 'logger.' not in line:
                continue
            # phone_number_id é identificador da API, não dado pessoal
            cleaned = line.replace('phone_number_id', '')
            if 'phone_number' in cleaned and 'mask_phone' not in line:
                self.fail(f"Telefone bruto em log: {line.strip()}")
