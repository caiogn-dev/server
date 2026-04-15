from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.stores.admin import StoreAdminForm, StoreIntegrationAdminForm
from apps.stores.models import Store, StoreIntegration

User = get_user_model()


class StoreAdminFormTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='storeadmin',
            email='storeadmin@example.com',
            password='testpass123',
        )
        self.store = Store.objects.create(
            name='Ce Saladas',
            slug='ce-saladas',
            store_type=Store.StoreType.FOOD,
            status=Store.StoreStatus.ACTIVE,
            owner=self.user,
            metadata={'existing': 'value'},
        )

    def _store_form_data(self, **overrides):
        data = {
            'name': self.store.name,
            'slug': self.store.slug,
            'description': self.store.description,
            'store_type': self.store.store_type,
            'status': self.store.status,
            'owner': str(self.user.pk),
            'email': self.store.email,
            'phone': self.store.phone,
            'whatsapp_number': self.store.whatsapp_number,
            'address': self.store.address,
            'city': self.store.city,
            'state': self.store.state,
            'zip_code': self.store.zip_code,
            'country': self.store.country,
            'latitude': self.store.latitude or '',
            'longitude': self.store.longitude or '',
            'currency': self.store.currency,
            'timezone': self.store.timezone,
            'tax_rate': str(self.store.tax_rate),
            'delivery_enabled': self.store.delivery_enabled,
            'pickup_enabled': self.store.pickup_enabled,
            'min_order_value': str(self.store.min_order_value),
            'free_delivery_threshold': self.store.free_delivery_threshold or '',
            'default_delivery_fee': str(self.store.default_delivery_fee),
            'operating_hours': self.store.operating_hours,
            'metadata': self.store.metadata,
            'primary_color': self.store.primary_color,
            'secondary_color': self.store.secondary_color,
            'logo_url': self.store.logo_url,
            'banner_url': self.store.banner_url,
            'is_active': self.store.is_active,
            'frontend_url': '',
        }
        data.update(overrides)
        return data

    def test_store_admin_form_persists_frontend_url_in_metadata(self):
        form = StoreAdminForm(
            data=self._store_form_data(frontend_url='https://cesaladas.com.br'),
            instance=self.store,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved_store = form.save()

        self.assertEqual(saved_store.metadata['frontend_url'], 'https://cesaladas.com.br')
        self.assertEqual(saved_store.metadata['existing'], 'value')

    def test_store_admin_form_can_clear_frontend_url_without_losing_metadata(self):
        self.store.metadata['frontend_url'] = 'https://old.cesaladas.com.br'
        self.store.save(update_fields=['metadata'])

        form = StoreAdminForm(
            data=self._store_form_data(frontend_url=''),
            instance=self.store,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved_store = form.save()

        self.assertNotIn('frontend_url', saved_store.metadata)
        self.assertEqual(saved_store.metadata['existing'], 'value')


class StoreIntegrationAdminFormTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='integrationadmin',
            email='integrationadmin@example.com',
            password='testpass123',
        )
        self.store = Store.objects.create(
            name='Ce Saladas',
            slug='ce-saladas',
            store_type=Store.StoreType.FOOD,
            status=Store.StoreStatus.ACTIVE,
            owner=self.user,
        )
        self.integration = StoreIntegration.objects.create(
            store=self.store,
            integration_type=StoreIntegration.IntegrationType.MERCADOPAGO,
            name='Mercado Pago - Ce Saladas',
            status=StoreIntegration.IntegrationStatus.ACTIVE,
            settings={},
        )

    def _integration_form_data(self, **overrides):
        data = {
            'store': str(self.store.pk),
            'integration_type': self.integration.integration_type,
            'name': self.integration.name,
            'status': self.integration.status,
            'is_active': self.integration.is_active,
            'public_key': '',
            'access_token': '',
            'webhook_secret': '',
            'webhook_verify_token': '',
            'webhook_url': '',
            'sandbox': False,
            'external_id': self.integration.external_id,
            'phone_number_id': self.integration.phone_number_id,
            'waba_id': self.integration.waba_id,
            'token_expires_at': self.integration.token_expires_at or '',
            'settings': self.integration.settings,
            'metadata': self.integration.metadata,
        }
        data.update(overrides)
        return data

    def test_store_integration_admin_form_prefills_existing_credentials(self):
        self.integration.api_key = 'APP_USR-existing-public'
        self.integration.access_token = 'APP_USR-existing-access'
        self.integration.settings = {'sandbox': True}
        self.integration.save()

        form = StoreIntegrationAdminForm(instance=self.integration)

        self.assertEqual(form.fields['public_key'].initial, 'APP_USR-existing-public')
        self.assertEqual(form.fields['access_token'].initial, 'APP_USR-existing-access')
        self.assertTrue(form.fields['sandbox'].initial)

    @override_settings(BASE_URL='https://backend.pastita.com.br')
    def test_store_integration_admin_form_persists_credentials_and_settings(self):
        webhook_url = 'https://backend.pastita.com.br/api/v1/stores/ce-saladas/webhooks/mercadopago/'
        form = StoreIntegrationAdminForm(
            data=self._integration_form_data(
                public_key='APP_USR-27d0fb2f-944a-4fa2-b45e-1eb5e64830e4',
                access_token='APP_USR-7044593645627225-041514-token',
                webhook_secret='395eef26403a7b6d55b1ed3a5122a1878132e13b20ca81b25024c2ef50afba85',
                webhook_url=webhook_url,
                sandbox=True,
            ),
            instance=self.integration,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved_integration = form.save()

        self.assertEqual(saved_integration.api_key, 'APP_USR-27d0fb2f-944a-4fa2-b45e-1eb5e64830e4')
        self.assertNotEqual(saved_integration.api_key_encrypted, 'APP_USR-27d0fb2f-944a-4fa2-b45e-1eb5e64830e4')
        self.assertEqual(saved_integration.access_token, 'APP_USR-7044593645627225-041514-token')
        self.assertNotEqual(saved_integration.access_token_encrypted, 'APP_USR-7044593645627225-041514-token')
        self.assertEqual(
            saved_integration.webhook_secret,
            '395eef26403a7b6d55b1ed3a5122a1878132e13b20ca81b25024c2ef50afba85',
        )
        self.assertEqual(saved_integration.settings['public_key'], 'APP_USR-27d0fb2f-944a-4fa2-b45e-1eb5e64830e4')
        self.assertTrue(saved_integration.settings['sandbox'])
        self.assertEqual(saved_integration.settings['webhook_url'], webhook_url)
        self.assertEqual(saved_integration.settings['notification_url'], webhook_url)
