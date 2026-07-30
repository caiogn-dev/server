"""Re-engajamento multi-tenant (30/jul): fim do "que tal uma salada" hardcoded.

A mensagem de "sentimos sua falta" era um texto fixo de salada + botão
"Montar Salada" para TODAS as lojas (a Pastita mandava salada pra quem
compra rondelli). Agora o corpo cita a loja e um produto dela (destaque
primeiro), e os botões respeitam o CTA custom de settings['bot_cta'].
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.tasks.automation_tasks import _reengagement_content

User = get_user_model()


class ReengagementContentTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='donor1', email='donor1@loja.com', password='x'
        )
        self.store = Store.objects.create(
            billing_exempt=True,
            name='Pastita', slug='pastita-reeng', owner=self.owner,
        )
        self.profile = CompanyProfile.objects.get(store=self.store)

    def test_body_uses_store_product_not_salad(self):
        StoreProduct.objects.create(
            store=self.store, name='Rondelli de Queijo', slug='rondelli-q',
            price=48, is_active=True,
        )
        body, buttons = _reengagement_content(self.store, self.profile)
        self.assertIn('Rondelli de Queijo', body)
        self.assertIn('Pastita', body)
        self.assertNotIn('salada', body.lower())
        self.assertEqual([b['id'] for b in buttons], ['view_menu'])

    def test_featured_product_wins(self):
        StoreProduct.objects.create(
            store=self.store, name='Panqueca', slug='panqueca',
            price=30, is_active=True,
        )
        StoreProduct.objects.create(
            store=self.store, name='Rondelli de Queijo', slug='rondelli-q2',
            price=48, is_active=True, featured=True,
        )
        body, _ = _reengagement_content(self.store, self.profile)
        self.assertIn('Rondelli de Queijo', body)

    def test_inactive_products_ignored(self):
        StoreProduct.objects.create(
            store=self.store, name='Extinto', slug='extinto',
            price=10, is_active=False,
        )
        body, _ = _reengagement_content(self.store, self.profile)
        self.assertNotIn('Extinto', body)
        self.assertIn('Pastita', body)  # fallback genérico ainda cita a loja

    def test_custom_bot_cta_button_respected(self):
        self.profile.settings = {'bot_cta': {'id': 'montar_salada', 'title': '🥗 Montar Salada'}}
        self.profile.save()
        _, buttons = _reengagement_content(self.store, self.profile)
        self.assertEqual(
            [b['id'] for b in buttons], ['view_menu', 'montar_salada']
        )
