"""Reimprimir deve criar job NOVO — o agent ignora id repetido como duplicata."""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct
from apps.stores.models.printing import StorePrintJob
from apps.stores.services.print_service import enqueue_order_print_job

User = get_user_model()


class PrintRequeueTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-req', email='owner-req@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Req', slug='loja-req', owner=self.owner, status='active',
        )
        category = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        product = StoreProduct.objects.create(
            store=self.store, name='Item', price=10, track_stock=False, category=category,
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='C', customer_phone='0',
            customer_email='c@local.invalid', subtotal=10, total=10,
            payment_method='cash', delivery_method='pickup',
            status='pending', payment_status='paid',
        )
        StoreOrderItem.objects.create(
            order=self.order, product=product, product_name='Item',
            unit_price=10, quantity=1, subtotal=10,
        )
        self.client.force_authenticate(self.owner)

    def test_requeue_cria_job_novo_sem_dedupe(self):
        original = enqueue_order_print_job(
            self.order, station='balcao',
            template=StorePrintJob.Template.CUSTOMER_RECEIPT,
        ).job
        resp = self.client.post(f'/api/v1/stores/print-jobs/{original.id}/requeue/', {}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertNotEqual(resp.data['id'], str(original.id))
        novo = StorePrintJob.objects.get(id=resp.data['id'])
        self.assertEqual(novo.template, StorePrintJob.Template.CUSTOMER_RECEIPT)
        self.assertEqual(novo.station, 'balcao')
        self.assertEqual(novo.source, StorePrintJob.Source.MANUAL_REPRINT)
        self.assertEqual(novo.dedupe_key, '')
        self.assertEqual(novo.status, StorePrintJob.JobStatus.PENDING)
