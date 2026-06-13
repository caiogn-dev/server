"""Máscara de PII para logs (LGPD art. 46 — boas práticas)."""
from django.test import SimpleTestCase

from apps.core.pii import mask_phone, mask_email, mask_cpf, mask_pii


class PiiMaskingTests(SimpleTestCase):
    def test_mask_phone(self):
        self.assertEqual(mask_phone('5599888887777'), '55*******7777')
        self.assertEqual(mask_phone(''), '')

    def test_mask_email(self):
        self.assertEqual(mask_email('joao.silva@gmail.com'), 'j***@gmail.com')
        self.assertEqual(mask_email('a@b.com'), 'a***@b.com')

    def test_mask_cpf(self):
        self.assertEqual(mask_cpf('12345678901'), '***.***.**9-01')

    def test_mask_pii_dict(self):
        masked = mask_pii({'phone': '5599888887777', 'email': 'x@y.com', 'name': 'João'})
        self.assertNotIn('888887', masked['phone'])
        self.assertTrue(masked['email'].startswith('x***'))
