from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.stores.models import Store

User = get_user_model()


class StoreAutomationConfigTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='auto-owner', password='x')

    def test_store_tem_campos_de_automacao(self):
        store = Store.objects.create(
            name='Auto Test', slug='auto-test', owner=self.owner,
            status='active', store_type='food',
        )
        self.assertTrue(store.auto_reply_enabled)
        self.assertTrue(store.welcome_message_enabled)
        self.assertFalse(store.use_ai_agent)

    def test_store_automation_persiste(self):
        store = Store.objects.create(
            name='AI Test', slug='ai-test', owner=self.owner,
            status='active', store_type='food',
            use_ai_agent=True,
            auto_reply_enabled=False,
        )
        store.refresh_from_db()
        self.assertTrue(store.use_ai_agent)
        self.assertFalse(store.auto_reply_enabled)
