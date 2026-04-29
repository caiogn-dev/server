from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.stores.services.meta_pixel_service import send_purchase_event


class _Items:
    def all(self):
        return [
            SimpleNamespace(
                id='item-1',
                product_id='product-1',
                product_name='Salada Caesar',
                quantity=2,
                unit_price=15.50,
            )
        ]


def _order(slug='ce-saladas', metadata=None):
    return SimpleNamespace(
        id='order-uuid',
        order_number='CS-123',
        store=SimpleNamespace(slug=slug),
        customer_name='Maria Silva',
        customer_email='maria@example.com',
        customer_phone='+55 (63) 99999-0000',
        delivery_address={
            'city': 'Palmas',
            'state': 'TO',
            'zip_code': '77000-000',
        },
        total=42.50,
        metadata=metadata or {},
        items=_Items(),
        save=Mock(),
    )


def _request():
    return SimpleNamespace(
        META={
            'HTTP_X_FORWARDED_FOR': '203.0.113.10, 10.0.0.1',
            'HTTP_USER_AGENT': 'Mozilla/Test',
        },
        headers={
            'Referer': 'https://cesaladas.com.br/checkout',
        },
        build_absolute_uri=lambda: 'https://backend.pastita.com.br/api/v1/stores/ce-saladas/checkout/',
    )


class MetaConversionsApiTest(SimpleTestCase):
    @override_settings(
        META_PIXEL_ID='1301947998542003',
        META_CAPI_ACCESS_TOKEN='test-token',
        META_CAPI_VERSION='v20.0',
        META_CAPI_STORE_SLUGS=['ce-saladas'],
        META_CAPI_TEST_EVENT_CODE='',
    )
    @patch('apps.stores.services.meta_pixel_service.requests.post')
    def test_send_purchase_event_posts_meta_payload_and_marks_order(self, post):
        post.return_value = SimpleNamespace(ok=True, text='{}')
        order = _order()

        result = send_purchase_event(
            order,
            request=_request(),
            tracking_data={
                'event_id': 'Purchase:event-1',
                'fbp': 'fb.1.123.456',
                'fbc': 'fb.1.123.click',
            },
        )

        self.assertTrue(result)
        post.assert_called_once()
        _, kwargs = post.call_args
        self.assertEqual(kwargs['params']['access_token'], 'test-token')
        self.assertEqual(kwargs['json']['data'][0]['event_name'], 'Purchase')
        self.assertEqual(kwargs['json']['data'][0]['event_id'], 'Purchase:event-1')
        self.assertEqual(kwargs['json']['data'][0]['action_source'], 'website')
        self.assertEqual(kwargs['json']['data'][0]['event_source_url'], 'https://cesaladas.com.br/checkout')

        user_data = kwargs['json']['data'][0]['user_data']
        self.assertEqual(user_data['fbp'], 'fb.1.123.456')
        self.assertEqual(user_data['fbc'], 'fb.1.123.click')
        self.assertEqual(user_data['client_ip_address'], '203.0.113.10')
        self.assertEqual(user_data['client_user_agent'], 'Mozilla/Test')
        self.assertIn('em', user_data)
        self.assertIn('ph', user_data)

        custom_data = kwargs['json']['data'][0]['custom_data']
        self.assertEqual(custom_data['currency'], 'BRL')
        self.assertEqual(custom_data['value'], 42.50)
        self.assertEqual(custom_data['order_id'], 'CS-123')
        self.assertEqual(custom_data['num_items'], 2)

        order.save.assert_called_once_with(update_fields=['metadata', 'updated_at'])
        self.assertEqual(order.metadata['meta_capi']['purchase_event_id'], 'Purchase:event-1')

    @override_settings(
        META_PIXEL_ID='1301947998542003',
        META_CAPI_ACCESS_TOKEN='test-token',
        META_CAPI_VERSION='v20.0',
        META_CAPI_STORE_SLUGS=['ce-saladas'],
    )
    @patch('apps.stores.services.meta_pixel_service.requests.post')
    def test_send_purchase_event_skips_other_stores(self, post):
        result = send_purchase_event(_order(slug='pastita'), request=_request())

        self.assertFalse(result)
        post.assert_not_called()
