"""PDV: flag print_receipt deve gerar job de cupom (customer_receipt) no balcão."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreProduct
from apps.stores.models.printing import StorePrintJob

User = get_user_model()


class PdvPrintReceiptTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-cupom', email='owner-cupom@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Cupom', slug='loja-cupom', owner=self.owner, status='active',
        )
        category = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        self.product = StoreProduct.objects.create(
            store=self.store, name='Marmita', price=20, track_stock=False, category=category,
        )
        self.client.force_authenticate(self.owner)
        self.url = f'/api/v1/stores/{self.store.slug}/orders/'

    def _payload(self, **extra):
        return {
            'store': str(self.store.id),
            'customer_name': 'Cliente Balcão',
            'customer_phone': '00000000000',
            'delivery_method': 'pickup',
            'payment_method': 'cash',
            'items': [{'product_id': str(self.product.id), 'quantity': 1}],
            **extra,
        }

    def test_print_receipt_cria_job_de_cupom(self):
        # Celery é inalcançável no harness — qualquer .delay travaria 260s
        with patch('apps.stores.tasks.notify_new_order_push.delay'), \
                patch('apps.whatsapp.tasks.automation_tasks.notify_order_status_change.delay'), \
                self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(self.url, self._payload(print_receipt=True), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        jobs = StorePrintJob.objects.filter(
            store=self.store,
            template=StorePrintJob.Template.CUSTOMER_RECEIPT,
            station='balcao',
        )
        self.assertEqual(jobs.count(), 1)
        payload = jobs.first().payload
        self.assertEqual(payload['totals']['total'], '20.00')

    def test_sem_flag_nao_gera_cupom(self):
        # Celery é inalcançável no harness — qualquer .delay travaria 260s
        with patch('apps.stores.tasks.notify_new_order_push.delay'), \
                patch('apps.whatsapp.tasks.automation_tasks.notify_order_status_change.delay'), \
                self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(self.url, self._payload(), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertFalse(
            StorePrintJob.objects.filter(
                store=self.store,
                template=StorePrintJob.Template.CUSTOMER_RECEIPT,
            ).exists()
        )
