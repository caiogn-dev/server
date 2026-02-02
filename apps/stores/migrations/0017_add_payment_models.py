# Generated migration for payment models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0016_drop_ecommerce_coupon_table'),
    ]

    operations = [
        # Create StorePaymentGateway
        migrations.CreateModel(
            name='StorePaymentGateway',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('name', models.CharField(help_text='Display name for this gateway', max_length=255)),
                ('gateway_type', models.CharField(choices=[('stripe', 'Stripe'), ('mercadopago', 'Mercado Pago'), ('pagseguro', 'PagSeguro'), ('pix', 'PIX'), ('custom', 'Custom')], help_text='Payment gateway provider', max_length=20)),
                ('is_enabled', models.BooleanField(default=True, help_text='Whether this gateway is active')),
                ('is_sandbox', models.BooleanField(default=True, help_text='Use sandbox/test mode')),
                ('is_default', models.BooleanField(default=False, help_text='Use as default gateway for this store')),
                ('api_key', models.CharField(blank=True, help_text='API Key', max_length=500)),
                ('api_secret', models.CharField(blank=True, help_text='API Secret', max_length=500)),
                ('access_token', models.CharField(blank=True, help_text='Access Token (for MP)', max_length=500)),
                ('webhook_secret', models.CharField(blank=True, help_text='Webhook Secret', max_length=500)),
                ('public_key', models.CharField(blank=True, help_text='Public Key (for MP)', max_length=500)),
                ('endpoint_url', models.URLField(blank=True, help_text='Gateway API endpoint')),
                ('webhook_url', models.URLField(blank=True, help_text='Webhook URL for this gateway')),
                ('configuration', models.JSONField(blank=True, default=dict, help_text='Additional gateway-specific configuration')),
                ('store', models.ForeignKey(help_text='Store that owns this gateway configuration', on_delete=django.db.models.deletion.CASCADE, related_name='payment_gateways', to='stores.store')),
            ],
            options={
                'verbose_name': 'Payment Gateway',
                'verbose_name_plural': 'Payment Gateways',
                'db_table': 'store_payment_gateways',
                'ordering': ['-is_default', 'name'],
            },
        ),
        
        # Create StorePayment
        migrations.CreateModel(
            name='StorePayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('payment_id', models.CharField(db_index=True, help_text='Internal payment ID (UUID)', max_length=100, unique=True)),
                ('external_id', models.CharField(blank=True, db_index=True, help_text='External payment ID (from gateway)', max_length=255)),
                ('external_reference', models.CharField(blank=True, help_text='External reference (order number)', max_length=255)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed'), ('cancelled', 'Cancelled'), ('refunded', 'Refunded'), ('partially_refunded', 'Partially Refunded')], db_index=True, default='pending', max_length=20)),
                ('payment_method', models.CharField(blank=True, choices=[('credit_card', 'Credit Card'), ('debit_card', 'Debit Card'), ('pix', 'PIX'), ('boleto', 'Boleto'), ('cash', 'Cash'), ('bank_transfer', 'Bank Transfer'), ('wallet', 'Digital Wallet'), ('other', 'Other')], help_text='Payment method used', max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, help_text='Payment amount', max_digits=10)),
                ('currency', models.CharField(default='BRL', help_text='Currency code', max_length=3)),
                ('fee', models.DecimalField(decimal_places=2, default=0, help_text='Gateway fee', max_digits=10)),
                ('net_amount', models.DecimalField(decimal_places=2, default=0, help_text='Amount after fees', max_digits=10)),
                ('refunded_amount', models.DecimalField(decimal_places=2, default=0, help_text='Total refunded amount', max_digits=10)),
                ('payer_email', models.EmailField(blank=True, help_text='Payer email', max_length=254)),
                ('payer_name', models.CharField(blank=True, help_text='Payer name', max_length=255)),
                ('payer_document', models.CharField(blank=True, help_text='CPF/CNPJ', max_length=50)),
                ('payment_url', models.URLField(blank=True, help_text='Payment URL for customer')),
                ('qr_code', models.TextField(blank=True, help_text='PIX QR code text')),
                ('qr_code_base64', models.TextField(blank=True, help_text='PIX QR code base64 image')),
                ('barcode', models.CharField(blank=True, help_text='Boleto barcode', max_length=255)),
                ('ticket_url', models.URLField(blank=True, help_text='Boleto/PDF URL')),
                ('expires_at', models.DateTimeField(blank=True, help_text='Payment expiration', null=True)),
                ('paid_at', models.DateTimeField(blank=True, help_text='When payment was confirmed', null=True)),
                ('refunded_at', models.DateTimeField(blank=True, help_text='When refund was processed', null=True)),
                ('gateway_response', models.JSONField(blank=True, default=dict, help_text='Full gateway response')),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Additional metadata')),
                ('error_code', models.CharField(blank=True, help_text='Error code if failed', max_length=50)),
                ('error_message', models.TextField(blank=True, help_text='Error message if failed')),
                ('gateway', models.ForeignKey(blank=True, help_text='Payment gateway used', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payments', to='stores.storepaymentgateway')),
                ('order', models.ForeignKey(help_text='Order this payment belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='stores.storeorder')),
            ],
            options={
                'verbose_name': 'Payment',
                'verbose_name_plural': 'Payments',
                'db_table': 'store_payments',
                'ordering': ['-created_at'],
            },
        ),
        
        # Create StorePaymentWebhookEvent
        migrations.CreateModel(
            name='StorePaymentWebhookEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event_id', models.CharField(db_index=True, help_text='External event ID', max_length=100)),
                ('event_type', models.CharField(help_text='Event type (e.g., payment.created)', max_length=100)),
                ('processing_status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'completed'), ('failed', 'Failed'), ('duplicate', 'Duplicate'), ('ignored', 'Ignored')], default='pending', max_length=20)),
                ('payload', models.JSONField(help_text='Full webhook payload')),
                ('headers', models.JSONField(blank=True, default=dict, help_text='Request headers')),
                ('processed_at', models.DateTimeField(blank=True, help_text='When event was processed', null=True)),
                ('retry_count', models.PositiveIntegerField(default=0, help_text='Number of retry attempts')),
                ('error_message', models.TextField(blank=True, help_text='Error message if processing failed')),
                ('gateway', models.ForeignKey(help_text='Gateway that received this event', on_delete=django.db.models.deletion.CASCADE, related_name='webhook_events', to='stores.storepaymentgateway')),
                ('order', models.ForeignKey(blank=True, help_text='Related order (if identified)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payment_webhook_events', to='stores.storeorder')),
                ('payment', models.ForeignKey(blank=True, help_text='Related payment (if identified)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='webhook_events', to='stores.storepayment')),
            ],
            options={
                'verbose_name': 'Payment Webhook Event',
                'verbose_name_plural': 'Payment Webhook Events',
                'db_table': 'store_payment_webhook_events',
                'ordering': ['-created_at'],
            },
        ),
        
        # Add indexes
        migrations.AddIndex(
            model_name='storepaymentgateway',
            index=models.Index(fields=['store', 'is_enabled'], name='stores_stpay_store_i_7f3f6b_idx'),
        ),
        migrations.AddIndex(
            model_name='storepaymentgateway',
            index=models.Index(fields=['store', 'gateway_type'], name='stores_stpay_store_i_8a4e2c_idx'),
        ),
        migrations.AddIndex(
            model_name='storepaymentgateway',
            index=models.Index(fields=['gateway_type', 'is_enabled'], name='stores_stpay_gateway_3d5a1b_idx'),
        ),
        migrations.AddIndex(
            model_name='storepayment',
            index=models.Index(fields=['order', 'status'], name='stores_stpay_order_i_9b6c3d_idx'),
        ),
        migrations.AddIndex(
            model_name='storepayment',
            index=models.Index(fields=['external_id'], name='stores_stpay_externa_2e7f4a_idx'),
        ),
        migrations.AddIndex(
            model_name='storepayment',
            index=models.Index(fields=['gateway', 'status'], name='stores_stpay_gateway_4c8d2e_idx'),
        ),
        migrations.AddIndex(
            model_name='storepayment',
            index=models.Index(fields=['status', 'created_at'], name='stores_stpay_status__5a9e1b_idx'),
        ),
        migrations.AddIndex(
            model_name='storepayment',
            index=models.Index(fields=['payment_method', 'status'], name='stores_stpay_payment_6b2f5c_idx'),
        ),
        migrations.AddIndex(
            model_name='storepaymentwebhookevent',
            index=models.Index(fields=['gateway', 'event_type'], name='stores_stpay_gateway_7d3a8f_idx'),
        ),
        migrations.AddIndex(
            model_name='storepaymentwebhookevent',
            index=models.Index(fields=['processing_status', 'created_at'], name='stores_stpay_processi_8e4b9c_idx'),
        ),
        migrations.AddIndex(
            model_name='storepaymentwebhookevent',
            index=models.Index(fields=['event_id', 'gateway'], name='stores_stpay_event_i_9f5c0d_idx'),
        ),
        migrations.AddIndex(
            model_name='storepaymentwebhookevent',
            index=models.Index(fields=['payment', 'event_type'], name='stores_stpay_payment_a1b6d2_idx'),
        ),
        
        # Add unique constraints
        migrations.AddConstraint(
            model_name='storepaymentgateway',
            constraint=models.UniqueConstraint(condition=models.Q(('is_enabled', True)), fields=('store', 'gateway_type'), name='unique_gateway_type_per_store'),
        ),
        migrations.AddConstraint(
            model_name='storepaymentwebhookevent',
            constraint=models.UniqueConstraint(fields=('gateway', 'event_id'), name='unique_event_per_gateway'),
        ),
    ]
