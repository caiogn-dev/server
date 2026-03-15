from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import Store, StoreIntegration, StorePaymentGateway
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class StorefrontBootstrapAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='storefront-user',
            email='storefront@example.com',
            password='testpass123',
            first_name='Caio',
            last_name='Graco',
        )
        self.token = Token.objects.create(user=self.user)

        self.whatsapp_account = WhatsAppAccount.objects.create(
            name='CE Saladas WA',
            phone_number_id='wa-phone-123',
            waba_id='wa-business-123',
            phone_number='5563999999999',
            display_phone_number='+55 63 99999-9999',
            access_token_encrypted='stub-token',
            status=WhatsAppAccount.AccountStatus.ACTIVE,
            owner=self.user,
        )

        self.store = Store.objects.create(
            name='CE Saladas',
            slug='ce-saladas-test',
            description='Saladas frescas',
            store_type=Store.StoreType.FOOD,
            status=Store.StoreStatus.ACTIVE,
            owner=self.user,
            currency='BRL',
            timezone='America/Sao_Paulo',
            city='Palmas',
            state='TO',
            address='Quadra 104 Sul, Rua SE 5',
            phone='6332100000',
            whatsapp_number='63999999999',
            latitude=Decimal('-10.1847000'),
            longitude=Decimal('-48.3337000'),
            primary_color='#0B3D2E',
            secondary_color='#D7F171',
            min_order_value=Decimal('25.00'),
            default_delivery_fee=Decimal('8.00'),
            metadata={
                'max_delivery_distance_km': 12,
                'max_delivery_time_minutes': 40,
                'cash_enabled': True,
            },
            whatsapp_account=self.whatsapp_account,
        )

        self.gateway = StorePaymentGateway.objects.create(
            store=self.store,
            name='Mercado Pago',
            gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
            is_enabled=True,
            is_sandbox=True,
            is_default=True,
            public_key='APP_USR-public-key',
        )

        self.integration = StoreIntegration.objects.create(
            store=self.store,
            integration_type=StoreIntegration.IntegrationType.MERCADOPAGO,
            name='Mercado Pago',
            status=StoreIntegration.IntegrationStatus.ACTIVE,
        )
        self.integration.access_token = 'APP_USR-secret-token'
        self.integration.save(update_fields=['access_token_encrypted', 'updated_at'])

    def test_app_config_exposes_only_public_bootstrap_data(self):
        response = self.client.get(f'/api/v1/stores/{self.store.slug}/app-config/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['auth']['whatsapp_account_id'], str(self.whatsapp_account.id))
        self.assertTrue(response.data['auth']['whatsapp_otp_enabled'])
        self.assertIn('pix', response.data['payment']['enabled_methods'])
        self.assertIn('credit_card', response.data['payment']['enabled_methods'])
        self.assertEqual(
            response.data['payment']['mercado_pago']['public_key'],
            self.gateway.public_key,
        )
        self.assertTrue(response.data['payment']['mercado_pago']['native_card_supported'])

        payload_as_string = str(response.data)
        self.assertNotIn('APP_USR-secret-token', payload_as_string)
        self.assertNotIn('access_token', payload_as_string)
        self.assertEqual(response.data['delivery']['city'], 'Palmas')
        self.assertEqual(response.data['delivery']['state'], 'TO')

    def test_customer_profile_returns_merged_store_and_user_data(self):
        CustomerIdentityService.sync_checkout_customer(
            store=self.store,
            customer_name='Caio Graco',
            email='storefront@example.com',
            phone='(63) 99999-9999',
            cpf='12345678909',
            delivery_method='delivery',
            delivery_address={
                'street': 'Quadra 104 Sul',
                'number': '12',
                'neighborhood': 'Plano Diretor Sul',
                'city': 'Palmas',
                'state': 'TO',
                'zip_code': '77020026',
            },
            user=self.user,
        )

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        response = self.client.get(f'/api/v1/stores/{self.store.slug}/customer/profile/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['contact']['name'], 'Caio Graco')
        self.assertEqual(response.data['contact']['email'], 'storefront@example.com')
        self.assertTrue(response.data['contact']['phone'].endswith('999999999'))
        self.assertEqual(len(response.data['addresses']), 1)
        self.assertEqual(response.data['default_address']['city'], 'Palmas')
        self.assertEqual(response.data['default_address']['state'], 'TO')

    def test_customer_profile_patch_updates_profile_and_store_customer(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        payload = {
            'customer_name': 'Caio Graco',
            'customer_email': 'storefront@example.com',
            'customer_phone': '(63) 99999-9999',
            'cpf': '12345678909',
            'address': {
                'street': 'Alameda 12',
                'number': '45',
                'neighborhood': 'Plano Diretor Norte',
                'zip_code': '77001000',
                'city': 'Palmas',
                'state': 'TO',
                'reference': 'Perto da praca',
            },
            'default_address_index': 0,
            'accepts_marketing': True,
        }

        response = self.client.patch(
            f'/api/v1/stores/{self.store.slug}/customer/profile/',
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['preferences']['accepts_marketing'], True)
        self.assertEqual(response.data['default_address']['street'], 'Alameda 12')
        self.assertEqual(response.data['default_address']['state'], 'TO')

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'storefront@example.com')
