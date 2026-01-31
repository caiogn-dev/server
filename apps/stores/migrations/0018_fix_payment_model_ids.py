# Fix payment model IDs - drop and recreate with UUID
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ('stores', '0017_add_payment_models'),
    ]

    operations = [
        # Delete old tables with bigint IDs and recreate with UUID
        migrations.DeleteModel(
            name='StorePaymentWebhookEvent',
        ),
        migrations.DeleteModel(
            name='StorePayment',
        ),
        migrations.DeleteModel(
            name='StorePaymentGateway',
        ),
        
        # Recreate StorePaymentGateway with UUID
        migrations.CreateModel(
            name='StorePaymentGateway',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
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
        
        # Recreate StorePayment with UUID
        migrations.CreateModel(
            name='StorePayment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('amount', models.DecimalField(decimal_places=2, help_text='Payment amount', max_digits=10, validators=[django.core.validators.MinValueValidator(0.01)])),
                ('currency', models.CharField(default='BRL', help_text='Currency code (ISO 4217)', max_length=3)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed'), ('refunded', 'Refunded'), ('cancelled', 'Cancelled')], default='pending', help_text='Current payment status', max_length=20)),
                ('payment_method', models.CharField(choices=[('credit_card', 'Credit Card'), ('debit_card', 'Debit Card'), ('pix', 'PIX'), ('boleto', 'Boleto'), ('wallet', 'Digital Wallet'), ('cash', 'Cash')], help_text='Payment method used', max_length=20)),
                ('external_id', models.CharField(blank=True, help_text='External payment ID from gateway', max_length=255)),
                ('external_url', models.URLField(blank=True, help_text='External payment URL (for PIX, Boleto)', max_length=500)),
                ('gateway_response', models.JSONField(blank=True, default=dict, help_text='Raw response from payment gateway')),
                ('error_message', models.TextField(blank=True, help_text='Error message if payment failed')),
                ('paid_at', models.DateTimeField(blank=True, help_text='When payment was confirmed', null=True)),
                ('gateway', models.ForeignKey(help_text='Payment gateway used', on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='stores.storepaymentgateway')),
                ('order', models.ForeignKey(help_text='Order being paid', on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='stores.storeorder')),
            ],
            options={
                'verbose_name': 'Payment',
                'verbose_name_plural': 'Payments',
                'db_table': 'store_payments',
                'ordering': ['-created_at'],
            },
        ),
        
        # Recreate StorePaymentWebhookEvent with UUID
        migrations.CreateModel(
            name='StorePaymentWebhookEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('event_type', models.CharField(help_text='Type of webhook event', max_length=100)),
                ('event_id', models.CharField(blank=True, help_text='External event ID', max_length=255)),
                ('payload', models.JSONField(help_text='Webhook payload')),
                ('processing_status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('processed', 'Processed'), ('failed', 'Failed'), ('ignored', 'Ignored')], default='pending', help_text='Processing status', max_length=20)),
                ('processed_at', models.DateTimeField(blank=True, help_text='When event was processed', null=True)),
                ('error_message', models.TextField(blank=True, help_text='Error message if processing failed')),
                ('gateway', models.ForeignKey(help_text='Payment gateway that sent this webhook', on_delete=django.db.models.deletion.CASCADE, related_name='webhook_events', to='stores.storepaymentgateway')),
                ('payment', models.ForeignKey(blank=True, help_text='Related payment (if identified)', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='webhook_events', to='stores.storepayment')),
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
            model_name='storepayment',
            index=models.Index(fields=['order', 'status'], name='store_pay_order_status_idx'),
        ),
        migrations.AddIndex(
            model_name='storepayment',
            index=models.Index(fields=['external_id'], name='store_pay_external_idx'),
        ),
        migrations.AddIndex(
            model_name='storepayment',
            index=models.Index(fields=['gateway', 'status'], name='store_pay_gateway_status_idx'),
        ),
        migrations.AddIndex(
            model_name='storepaymentgateway',
            index=models.Index(fields=['store', 'is_enabled'], name='store_pay_gateway_store_idx'),
        ),
        migrations.AddIndex(
            model_name='storepaymentwebhookevent',
            index=models.Index(fields=['gateway', 'processing_status'], name='store_pay_webhook_gateway_idx'),
        ),
        migrations.AddIndex(
            model_name='storepaymentwebhookevent',
            index=models.Index(fields=['event_id'], name='store_pay_webhook_event_idx'),
        ),
    ]
