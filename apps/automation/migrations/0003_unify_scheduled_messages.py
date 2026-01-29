# Generated migration to unify ScheduledMessage models
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('automation', '0002_add_scheduled_messages_and_reports'),
        ('whatsapp', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Rename the table from automation_scheduled_messages to scheduled_messages
        migrations.AlterModelTable(
            name='scheduledmessage',
            table='scheduled_messages',
        ),
        
        # Change related_name from 'automation_scheduled_messages' to 'scheduled_messages'
        migrations.AlterField(
            model_name='scheduledmessage',
            name='account',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='scheduled_messages',
                to='whatsapp.whatsappaccount'
            ),
        ),
        
        # Change related_name for created_by
        migrations.AlterField(
            model_name='scheduledmessage',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='scheduled_messages',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        
        # Add content field
        migrations.AddField(
            model_name='scheduledmessage',
            name='content',
            field=models.JSONField(blank=True, default=dict, help_text='Additional content data'),
        ),
        
        # Add error_code field
        migrations.AddField(
            model_name='scheduledmessage',
            name='error_code',
            field=models.CharField(blank=True, max_length=50),
        ),
        
        # Add recurrence fields
        migrations.AddField(
            model_name='scheduledmessage',
            name='is_recurring',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='scheduledmessage',
            name='recurrence_rule',
            field=models.CharField(blank=True, help_text='RRULE format', max_length=255),
        ),
        migrations.AddField(
            model_name='scheduledmessage',
            name='next_occurrence',
            field=models.DateTimeField(blank=True, null=True),
        ),
        
        # Add source tracking fields
        migrations.AddField(
            model_name='scheduledmessage',
            name='source',
            field=models.CharField(default='manual', help_text='Source: manual, campaign, automation, api', max_length=20),
        ),
        migrations.AddField(
            model_name='scheduledmessage',
            name='campaign_id',
            field=models.UUIDField(blank=True, help_text='Related campaign if from campaign', null=True),
        ),
        
        # Add new index for source
        migrations.AddIndex(
            model_name='scheduledmessage',
            index=models.Index(fields=['source', 'status'], name='scheduled_m_source_a1b2c3_idx'),
        ),
    ]
