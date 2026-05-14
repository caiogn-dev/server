"""
Migração inicial do app messenger — Facebook Messenger Platform.
"""
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('agents', '0007_agent_owner'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MessengerAccount',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('name', models.CharField(max_length=255)),
                ('page_id', models.CharField(db_index=True, max_length=50, unique=True)),
                ('page_name', models.CharField(max_length=255)),
                ('page_access_token', models.TextField()),
                ('status', models.CharField(
                    choices=[('active', 'Active'), ('inactive', 'Inactive'), ('pending', 'Pending Verification')],
                    default='pending',
                    max_length=20,
                )),
                ('webhook_verified', models.BooleanField(default=False)),
                ('auto_response_enabled', models.BooleanField(default=True)),
                ('human_handoff_enabled', models.BooleanField(default=True)),
                ('default_agent', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='messenger_accounts',
                    to='agents.agent',
                )),
                ('owner', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='messenger_accounts',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Messenger Account',
                'verbose_name_plural': 'Messenger Accounts',
                'db_table': 'messenger_accounts',
                'ordering': ['-created_at'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='MessengerConversation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('sender_id', models.CharField(db_index=True, max_length=50)),
                ('sender_name', models.CharField(max_length=255)),
                ('status', models.CharField(
                    choices=[('active', 'Active'), ('closed', 'Closed'), ('archived', 'Archived')],
                    default='active',
                    max_length=20,
                )),
                ('last_message', models.TextField(blank=True)),
                ('last_message_at', models.DateTimeField(blank=True, null=True)),
                ('unread_count', models.PositiveIntegerField(default=0)),
                ('is_bot_active', models.BooleanField(default=True)),
                ('handover_status', models.CharField(default='bot', help_text='bot, human, or pending', max_length=20)),
                ('account', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='conversations',
                    to='messenger.messengeraccount',
                )),
                ('assigned_to', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='messenger_conversations',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Messenger Conversation',
                'verbose_name_plural': 'Messenger Conversations',
                'db_table': 'messenger_conversations',
                'ordering': ['-updated_at'],
                'abstract': False,
            },
        ),
        migrations.AddConstraint(
            model_name='messengerconversation',
            constraint=models.UniqueConstraint(
                fields=['account', 'sender_id'],
                name='unique_messenger_conversation',
            ),
        ),
        migrations.CreateModel(
            name='MessengerMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('sender_id', models.CharField(max_length=50)),
                ('sender_name', models.CharField(max_length=255)),
                ('content', models.TextField()),
                ('message_type', models.CharField(
                    choices=[('text', 'Text'), ('image', 'Image'), ('video', 'Video'),
                             ('audio', 'Audio'), ('file', 'File'), ('template', 'Template')],
                    default='text',
                    max_length=20,
                )),
                ('media_url', models.URLField(blank=True)),
                ('attachments', models.JSONField(blank=True, default=list)),
                ('is_from_bot', models.BooleanField(default=False)),
                ('is_read', models.BooleanField(default=False)),
                ('mid', models.CharField(blank=True, db_index=True, max_length=100)),
                ('conversation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='messages',
                    to='messenger.messengerconversation',
                )),
            ],
            options={
                'verbose_name': 'Messenger Message',
                'verbose_name_plural': 'Messenger Messages',
                'db_table': 'messenger_messages',
                'ordering': ['created_at'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='MessengerBroadcast',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('name', models.CharField(max_length=255)),
                ('content', models.TextField()),
                ('message_type', models.CharField(
                    choices=[('text', 'Text'), ('image', 'Image'), ('video', 'Video'),
                             ('audio', 'Audio'), ('file', 'File'), ('template', 'Template')],
                    default='text',
                    max_length=20,
                )),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('scheduled', 'Scheduled'), ('sending', 'Sending'),
                             ('sent', 'Sent'), ('failed', 'Failed')],
                    default='draft',
                    max_length=20,
                )),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('recipient_count', models.PositiveIntegerField(default=0)),
                ('sent_count', models.PositiveIntegerField(default=0)),
                ('delivered_count', models.PositiveIntegerField(default=0)),
                ('failed_count', models.PositiveIntegerField(default=0)),
                ('account', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='broadcasts',
                    to='messenger.messengeraccount',
                )),
            ],
            options={
                'verbose_name': 'Messenger Broadcast',
                'verbose_name_plural': 'Messenger Broadcasts',
                'db_table': 'messenger_broadcasts',
                'ordering': ['-created_at'],
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='MessengerSponsoredMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('name', models.CharField(max_length=255)),
                ('content', models.TextField()),
                ('image_url', models.URLField(blank=True)),
                ('cta_type', models.CharField(default='LEARN_MORE', max_length=50)),
                ('cta_url', models.URLField(blank=True)),
                ('budget', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('currency', models.CharField(default='BRL', max_length=3)),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('pending', 'Pending'), ('active', 'Active'),
                             ('paused', 'Paused'), ('completed', 'Completed')],
                    default='draft',
                    max_length=20,
                )),
                ('account', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sponsored_messages',
                    to='messenger.messengeraccount',
                )),
            ],
            options={
                'verbose_name': 'Messenger Sponsored Message',
                'verbose_name_plural': 'Messenger Sponsored Messages',
                'db_table': 'messenger_sponsored_messages',
                'ordering': ['-created_at'],
                'abstract': False,
            },
        ),
    ]
