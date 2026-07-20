"""Regressão de segurança: is_staff burlava o escopo de loja em send_catalog_menu.

A action resolvia a Store por `store_id` e só filtrava por lojas acessíveis
quando `not (is_staff or is_superuser)`. Logo, qualquer conta is_staff enviava
o catálogo (produtos/preços) de QUALQUER loja pela sua PRÓPRIA conta WhatsApp,
bastando saber o UUID da loja. Só is_superuser deve selecionar loja alheia.

Cenários:
  1. Atacante is_staff, com conta própria, NÃO resolve a loja da vítima
     (400 'Loja não encontrada') — antes do fix a loja resolvia e seguia o envio.
  2. superuser continua podendo selecionar qualquer loja (guarda de regressão).
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.tests.factories import make_product
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

URL = '/api/v1/whatsapp/messages/send_catalog_menu/'


class SendCatalogMenuStaffIDORTest(APITestCase):
    def setUp(self):
        self.victim = User.objects.create_user(username='cm-victim', email='v@t.com', password='x')
        self.victim_store = Store.objects.create(
            name='Loja Vitima', slug='cm-vitima', owner=self.victim, status='active',
        )
        make_product(self.victim_store, name='Marmita Secreta')

        # Atacante is_staff com a PRÓPRIA conta WhatsApp (passa _check_account_access).
        self.attacker = User.objects.create_user(
            username='cm-att', email='a@t.com', password='x', is_staff=True,
        )
        self.attacker_acc = WhatsAppAccount.objects.create(
            name='att', phone_number_id='pn-a', waba_id='wa-a',
            phone_number='+5511000111', display_phone_number='+5511000111',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.attacker,
        )
        self.superuser = User.objects.create_superuser(username='cm-super', email='s@t.com', password='x')

    def _payload(self):
        return {
            'account_id': str(self.attacker_acc.id),
            'to': '+5511999998888',
            'store_id': str(self.victim_store.id),
        }

    def test_staff_nao_resolve_loja_alheia(self):
        """is_staff não pode selecionar a loja da vítima — 400 'Loja não encontrada'."""
        self.client.force_authenticate(self.attacker)
        with patch('apps.whatsapp.api.views.MessageService') as MS, \
             patch('apps.whatsapp.api.views.MessageSerializer') as MSer:
            MS.return_value.send_catalog_message.return_value = object()
            MSer.return_value.data = {'ok': True}
            resp = self.client.post(URL, self._payload(), format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('não encontrada', str(resp.data))
        MS.return_value.send_catalog_message.assert_not_called()

    def test_superuser_pode_selecionar_qualquer_loja(self):
        """Regressão: superuser continua podendo enviar catálogo de qualquer loja."""
        # superuser precisa de conta própria p/ passar _check_account_access
        su_acc = WhatsAppAccount.objects.create(
            name='su', phone_number_id='pn-su', waba_id='wa-su',
            phone_number='+5511000222', display_phone_number='+5511000222',
            access_token_encrypted='x', webhook_verify_token='x', owner=self.superuser,
        )
        self.client.force_authenticate(self.superuser)
        payload = self._payload()
        payload['account_id'] = str(su_acc.id)
        with patch('apps.whatsapp.api.views.MessageService') as MS, \
             patch('apps.whatsapp.api.views.MessageSerializer') as MSer:
            MS.return_value.send_catalog_message.return_value = object()
            MSer.return_value.data = {'ok': True}
            resp = self.client.post(URL, payload, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        MS.return_value.send_catalog_message.assert_called_once()
