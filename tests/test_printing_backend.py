"""
Backend tests for automatic order printing.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.stores.models import (
    Store,
    StoreCart,
    StoreCartItem,
    StoreOrder,
    StorePrintAgent,
    StorePrintJob,
    StoreProduct,
)
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.services.print_service import enqueue_order_print_job

User = get_user_model()


def _make_store(owner, slug='print-store'):
    return Store.objects.create(
        owner=owner,
        name='Cê Saladas',
        slug=slug,
        phone='6332110000',
        address='Quadra 706 Sul Alameda 2',
        city='Palmas',
        state='TO',
        is_active=True,
        default_delivery_fee=Decimal('12.50'),
    )


def _make_product(store, name='Especial Filé de Frango', price=Decimal('37.90')):
    return StoreProduct.objects.create(
        store=store,
        name=name,
        price=price,
        status=StoreProduct.ProductStatus.ACTIVE,
        track_stock=False,
    )


class PrintJobServiceTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('print-owner', 'print-owner@test.com', 'pass')
        self.customer = User.objects.create_user('print-customer', 'print-customer@test.com', 'pass')
        self.store = _make_store(self.owner)
        self.product = _make_product(self.store)

    def _make_order(self, *, delivery_method='delivery'):
        cart = StoreCart.objects.create(store=self.store, user=self.customer)
        StoreCartItem.objects.create(cart=cart, product=self.product, quantity=1)
        customer_data = {
            'name': 'Ana Paula',
            'email': 'ana@test.com',
            'phone': '556392064862',
        }
        delivery_data = {
            'method': delivery_method,
            'address': {
                'street': 'Quadra 706 Sul Alameda 2 lote 22',
                'number': '201',
                'complement': 'Apto B Residencial Classic',
                'city': 'Palmas',
                'state': 'TO',
            },
        } if delivery_method == 'delivery' else {'method': 'pickup'}

        with patch('apps.stores.services.checkout_service.trigger_order_email_automation'), \
             patch('apps.stores.tasks.notify_new_order_push.delay'), \
             self.captureOnCommitCallbacks(execute=True):
            return CheckoutService.create_order(cart, customer_data, delivery_data=delivery_data)

    def test_order_creation_enqueues_print_job_once(self):
        order = self._make_order()
        jobs = StorePrintJob.objects.filter(order=order)
        self.assertEqual(jobs.count(), 1)
        self.assertEqual(jobs.first().status, StorePrintJob.JobStatus.PENDING)
        result = enqueue_order_print_job(order)
        self.assertFalse(result.created)
        self.assertEqual(StorePrintJob.objects.filter(order=order).count(), 1)

    def test_pickup_payload_marks_retirada(self):
        order = self._make_order(delivery_method='pickup')
        job = StorePrintJob.objects.get(order=order)
        self.assertEqual(job.payload['order']['delivery_method'], StoreOrder.DeliveryMethod.PICKUP)
        self.assertEqual(job.payload['address_lines'], ['PEDIDO PARA RETIRADA'])


class PrintAgentApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user('agent-owner', 'agent-owner@test.com', 'pass')
        self.client.force_authenticate(user=self.owner)
        self.store = _make_store(self.owner, slug='agent-store')
        self.order = StoreOrder.objects.create(
            store=self.store,
            customer_name='Ana Paula',
            customer_email='ana@test.com',
            customer_phone='556392064862',
            subtotal=Decimal('37.90'),
            discount=Decimal('3.79'),
            tax=Decimal('0'),
            delivery_fee=Decimal('13.69'),
            total=Decimal('47.80'),
            payment_method='pix',
            delivery_method=StoreOrder.DeliveryMethod.DELIVERY,
            delivery_address={
                'street': 'Quadra 706 Sul Alameda 2 lote 22',
                'number': '201',
                'complement': 'Apto B Residencial Classic',
                'city': 'Palmas',
                'state': 'TO',
            },
        )
        self.job = enqueue_order_print_job(self.order).job

    def test_create_agent_returns_one_time_api_key(self):
        response = self.client.post('/api/v1/stores/print-agents/', {
            'store': str(self.store.id),
            'name': 'Cozinha Epson',
            'slug': 'cozinha-epson',
            'station': 'kitchen',
            'platform': 'windows',
            'connection_mode': 'windows_printer',
            'printer_name': 'EPSON TM-T20',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['api_key'].startswith('pa_'))

    def test_agent_claim_complete_and_fail_flow(self):
        raw_key = StorePrintAgent.objects.create(
            store=self.store,
            name='Agent',
            slug='agent-1',
            station='kitchen',
            printer_name='EPSON TM-T20',
            api_key_prefix='tmp',
            api_key_hash='tmp',
        ).rotate_api_key()

        claim = self.client.post(
            '/api/v1/stores/print/agent/claim-next/',
            {'app_version': '1.0.0', 'host_name': 'COZINHA-PC'},
            format='json',
            HTTP_X_PRINT_AGENT_KEY=raw_key,
        )
        self.assertEqual(claim.status_code, status.HTTP_200_OK)
        self.assertEqual(claim.data['job']['id'], str(self.job.id))

        complete = self.client.post(
            f'/api/v1/stores/print/jobs/{self.job.id}/complete/',
            {'printer_name': 'EPSON TM-T20'},
            format='json',
            HTTP_X_PRINT_AGENT_KEY=raw_key,
        )
        self.assertEqual(complete.status_code, status.HTTP_200_OK)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, StorePrintJob.JobStatus.COMPLETED)
        self.assertEqual(self.job.printer_name, 'EPSON TM-T20')

        reprint = self.client.post(f'/api/v1/stores/orders/{self.order.id}/reprint-kitchen-ticket/')
        self.assertEqual(reprint.status_code, status.HTTP_201_CREATED)
        new_job_id = reprint.data['id']

        second_claim = self.client.post(
            '/api/v1/stores/print/agent/claim-next/',
            {},
            format='json',
            HTTP_X_PRINT_AGENT_KEY=raw_key,
        )
        self.assertEqual(second_claim.status_code, status.HTTP_200_OK)
        self.assertEqual(second_claim.data['job']['id'], new_job_id)

        fail = self.client.post(
            f'/api/v1/stores/print/jobs/{new_job_id}/fail/',
            {'error': 'Printer offline', 'retryable': False},
            format='json',
            HTTP_X_PRINT_AGENT_KEY=raw_key,
        )
        self.assertEqual(fail.status_code, status.HTTP_200_OK)
        failed_job = StorePrintJob.objects.get(id=new_job_id)
        self.assertEqual(failed_job.status, StorePrintJob.JobStatus.FAILED)
        self.assertIn('Printer offline', failed_job.last_error)
