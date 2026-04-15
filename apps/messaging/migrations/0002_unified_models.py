# Generated migration for unified messaging models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0001_initial'),  # Adjust as needed
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('agents', '0001_initial'),  # Adjust as needed
        ('messaging', '0001_initial'),  # Previous messaging migration
    ]

    operations = [
        # Create PlatformAccount model
        migrations.CreateModel(
            name='PlatformAccount',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('platform', models.CharField(choices=[('whatsapp', 'WhatsApp'), ('instagram', 'Instagram'), ('messenger', 'Messenger')], db_index=True, max_length=20)),
                ('name', models.CharField(max_length=255)),
                ('external_id', models.CharField(db_index=True, max_length=255)),
                ('parent_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('phone_number', models.CharField(blank=True, max_length=20)),
                ('display_phone_number', models.CharField(blank=True, max_length=30)),
                ('access_token_encrypted', models.TextField(blank=True)),
                ('token_expires_at', models.DateTimeField(blank=True, null=True)),
                ('token_version', models.PositiveIntegerField(default=1)),
                ('webhook_verify_token', models.CharField(blank=True, max_length=255)),
                ('webhook_verified', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive'), ('pending', 'Pending Verification'), ('suspended', 'Suspended'), ('error', 'Error')], default='pending', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('is_verified', models.BooleanField(default=False)),
                ('auto_response_enabled', models.BooleanField(default=True)),
                ('human_handoff_enabled', models.BooleanField(default=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('last_sync_at', models.DateTimeField(blank=True, null=True)),
                ('last_error_at', models.DateTimeField(blank=True, null=True)),
                ('last_error_message', models.TextField(blank=True)),
                ('default_agent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='platform_accounts', to='agents.agent')),
                ('store', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='platform_accounts', to='stores.store')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='platform_accounts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Platform Account',
                'verbose_name_plural': 'Platform Accounts',
                'db_table': 'platform_accounts',
                'ordering': ['-created_at'],
            },
        ),
        
        # Create UnifiedConversation model
        migrations.CreateModel(
            name='UnifiedConversation',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('platform', models.CharField(choices=[('whatsapp', 'WhatsApp'), ('instagram', 'Instagram'), ('messenger', 'Messenger')], db_index=True, max_length=20)),
                ('external_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('customer_phone', models.CharField(db_index=True, max_length=20)),
                ('customer_name', models.CharField(blank=True, max_length=255)),
                ('customer_email', models.EmailField(blank=True)),
                ('customer_profile_pic', models.URLField(blank=True)),
                ('customer_platform_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('status', models.CharField(choices=[('active', 'Active'), ('archived', 'Archived'), ('blocked', 'Blocked')], default='active', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('unread_count', models.IntegerField(default=0)),
                ('assigned_at', models.DateTimeField(blank=True, null=True)),
                ('ai_enabled', models.BooleanField(default=True)),
                ('last_agent_response', models.DateTimeField(blank=True, null=True)),
                ('last_message_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('last_message_preview', models.TextField(blank=True)),
                ('source', models.CharField(default='organic', help_text='Source: organic, ad, campaign, etc', max_length=50)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_conversations', to=settings.AUTH_USER_MODEL)),
                ('platform_account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conversations', to='messaging.platformaccount')),
                ('store', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conversations', to='stores.store')),
            ],
            options={
                'verbose_name': 'Conversation',
                'verbose_name_plural': 'Conversations',
                'db_table': 'unified_conversations',
                'ordering': ['-last_message_at', '-created_at'],
            },
        ),
        
        # Create UnifiedMessage model
        migrations.CreateModel(
            name='UnifiedMessage',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('platform', models.CharField(choices=[('whatsapp', 'WhatsApp'), ('instagram', 'Instagram'), ('messenger', 'Messenger')], db_index=True, max_length=20)),
                ('direction', models.CharField(choices=[('inbound', 'Inbound'), ('outbound', 'Outbound')], db_index=True, max_length=10)),
                ('message_type', models.CharField(choices=[('text', 'Text'), ('image', 'Image'), ('video', 'Video'), ('audio', 'Audio'), ('document', 'Document'), ('sticker', 'Sticker'), ('location', 'Location'), ('contact', 'Contact'), ('template', 'Template'), ('interactive', 'Interactive'), ('button', 'Button'), ('reaction', 'Reaction'), ('order', 'Order'), ('system', 'System'), ('unknown', 'Unknown')], default='text', max_length=20)),
                ('text_body', models.TextField(blank=True)),
                ('content', models.JSONField(blank=True, default=dict)),
                ('media_url', models.URLField(blank=True)),
                ('media_mime_type', models.CharField(blank=True, max_length=100)),
                ('media_sha256', models.CharField(blank=True, max_length=64)),
                ('media_caption', models.TextField(blank=True)),
                ('template_name', models.CharField(blank=True, max_length=255)),
                ('template_language', models.CharField(blank=True, max_length=10)),
                ('template_components', models.JSONField(blank=True, default=list)),
                ('external_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('context_message_id', models.CharField(blank=True, max_length=255)),
                ('is_forwarded', models.BooleanField(default=False)),
                ('forwarded_count', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('sent', 'Sent'), ('delivered', 'Delivered'), ('read', 'Read'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('failed_at', models.DateTimeField(blank=True, null=True)),
                ('error_code', models.CharField(blank=True, max_length=50)),
                ('error_message', models.TextField(blank=True)),
                ('processed_by_agent', models.BooleanField(default=False, help_text='Message was processed by AI agent')),
                ('agent_id', models.CharField(blank=True, help_text='ID of agent that processed this message', max_length=100)),
                ('source', models.CharField(default='manual', help_text='Source: manual, automation, campaign, api, webhook', max_length=50)),
                ('campaign_id', models.UUIDField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('raw_webhook_data', models.JSONField(blank=True, default=dict, help_text='Raw data from platform webhook')),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='messaging.unifiedconversation')),
                ('platform_account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='messaging.platformaccount')),
            ],
            options={
                'verbose_name': 'Message',
                'verbose_name_plural': 'Messages',
                'db_table': 'unified_messages',
                'ordering': ['created_at'],
            },
        ),
        
        # Create UnifiedTemplate model
        migrations.CreateModel(
            name='UnifiedTemplate',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('platform', models.CharField(choices=[('whatsapp', 'WhatsApp'), ('instagram', 'Instagram'), ('messenger', 'Messenger'), ('email', 'Email'), ('sms', 'SMS')], default='whatsapp', max_length=20)),
                ('template_type', models.CharField(choices=[('standard', 'Standard'), ('carousel', 'Carousel'), ('lto', 'Limited Time Offer'), ('auth', 'Authentication'), ('order', 'Order Details'), ('catalog', 'Catalog')], default='standard', max_length=20)),
                ('name', models.CharField(max_length=255)),
                ('external_id', models.CharField(blank=True, help_text='Template ID from platform (e.g., Meta template ID)', max_length=255)),
                ('language', models.CharField(default='pt_BR', max_length=10)),
                ('category', models.CharField(choices=[('marketing', 'Marketing'), ('utility', 'Utility'), ('authentication', 'Authentication'), ('custom', 'Custom')], default='utility', max_length=20)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('pending', 'Pending Approval'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('paused', 'Paused')], default='draft', max_length=20)),
                ('header', models.JSONField(blank=True, default=dict, help_text='Header content (text, image, video, document)')),
                ('body', models.TextField(help_text='Main message body with {{variables}}')),
                ('footer', models.TextField(blank=True)),
                ('buttons', models.JSONField(blank=True, default=list, help_text='Button definitions')),
                ('components', models.JSONField(blank=True, default=list, help_text='Full components in Meta API format')),
                ('variables', models.JSONField(blank=True, default=list, help_text='List of variable names used in template')),
                ('sample_values', models.JSONField(blank=True, default=dict, help_text='Sample values for variables')),
                ('rejection_reason', models.TextField(blank=True)),
                ('version', models.CharField(default='1.0', max_length=10)),
                ('is_active', models.BooleanField(default=True)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('platform_account', models.ForeignKey(blank=True, help_text='Associated platform account (for WhatsApp)', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='templates', to='messaging.platformaccount')),
                ('store', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='templates', to='stores.store')),
            ],
            options={
                'verbose_name': 'Message Template',
                'verbose_name_plural': 'Message Templates',
                'db_table': 'unified_templates',
                'ordering': ['-created_at'],
            },
        ),
        
        # Add unique constraints
        migrations.AddConstraint(
            model_name='platformaccount',
            constraint=models.UniqueConstraint(fields=('platform', 'external_id'), name='unique_platform_external_id'),
        ),
        migrations.AddConstraint(
            model_name='unifiedconversation',
            constraint=models.UniqueConstraint(fields=('platform_account', 'customer_platform_id'), name='unique_conversation_customer'),
        ),
        migrations.AddConstraint(
            model_name='unifiedtemplate',
            constraint=models.UniqueConstraint(fields=('platform_account', 'name', 'language'), name='unique_template_name_lang'),
        ),
        
        # Add indexes
        migrations.AddIndex(
            model_name='platformaccount',
            index=models.Index(fields=['user', 'platform', 'status'], name='platform_account_user_plat_status'),
        ),
        migrations.AddIndex(
            model_name='platformaccount',
            index=models.Index(fields=['store', 'platform'], name='platform_account_store_plat'),
        ),
        migrations.AddIndex(
            model_name='unifiedconversation',
            index=models.Index(fields=['platform_account', 'customer_phone', '-created_at'], name='conv_plat_phone_created'),
        ),
        migrations.AddIndex(
            model_name='unifiedconversation',
            index=models.Index(fields=['status', 'is_active', '-last_message_at'], name='conv_status_active_last'),
        ),
        migrations.AddIndex(
            model_name='unifiedmessage',
            index=models.Index(fields=['conversation', '-created_at'], name='msg_conv_created'),
        ),
        migrations.AddIndex(
            model_name='unifiedmessage',
            index=models.Index(fields=['external_id', 'platform'], name='msg_ext_id_plat'),
        ),
    ]
