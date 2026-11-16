"""Campanha/automação de e-mail não aceitam template de outra loja."""
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from apps.marketing.models import EmailTemplate
from apps.stores.models import Store

User = get_user_model()


class TemplateDeOutraLojaTests(APITestCase):
    def setUp(self):
        self.dono_a = User.objects.create_user('a', 'a@x.com', 'pw')
        self.dono_b = User.objects.create_user('b', 'b@x.com', 'pw')
        self.loja_a = Store.objects.create(name='A', slug='loja-a', owner=self.dono_a)
        self.loja_b = Store.objects.create(name='B', slug='loja-b', owner=self.dono_b)
        self.tpl_a = EmailTemplate.objects.create(
            store=self.loja_a, name='ta', subject='s', html_content='<p>a</p>')
        self.tpl_b = EmailTemplate.objects.create(
            store=self.loja_b, name='segredo-b', subject='s', html_content='<p>b</p>')
        self.client = APIClient()
        self.client.force_authenticate(self.dono_a)

    def _campanha(self, tpl):
        return self.client.post('/api/v1/marketing/campaigns/', {
            'store': str(self.loja_a.id), 'name': 'c', 'subject': 's',
            'template': str(tpl.id), 'html_content': '<p>x</p>',
        }, format='json')

    def test_campanha_com_template_proprio_ok(self):
        self.assertEqual(self._campanha(self.tpl_a).status_code, 201)

    def test_campanha_com_template_de_outra_loja_recusada(self):
        r = self._campanha(self.tpl_b)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('template', r.json()['error']['details'])

    def test_automacao_com_template_de_outra_loja_recusada(self):
        r = self.client.post('/api/v1/marketing/automations/', {
            'store': str(self.loja_a.id), 'name': 'x', 'trigger_type': 'welcome',
            'subject': 's', 'html_content': '<p>x</p>', 'template': str(self.tpl_b.id),
        }, format='json')
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('template', r.json()['error']['details'])
