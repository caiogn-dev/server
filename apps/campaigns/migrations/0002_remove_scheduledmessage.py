# Migration to remove ScheduledMessage from campaigns app
# The model has been moved to apps.automation.models
# This migration removes the duplicate model definition

from django.db import migrations


class Migration(migrations.Migration):
    """
    Remove ScheduledMessage model from campaigns app.
    
    The ScheduledMessage model has been unified and moved to apps.automation.
    This migration removes the duplicate table created by campaigns app.
    
    Note: This migration assumes data has already been migrated to the
    automation.ScheduledMessage model (table: scheduled_messages).
    """

    dependencies = [
        ('campaigns', '0001_initial'),
        ('automation', '0003_unify_scheduled_messages'),  # Ensure automation has the unified model
    ]

    operations = [
        # Remove the indexes first
        migrations.RemoveIndex(
            model_name='scheduledmessage',
            name='campaigns_s_account_f1107f_idx',
        ),
        migrations.RemoveIndex(
            model_name='scheduledmessage',
            name='campaigns_s_schedul_8aa057_idx',
        ),
        # Then delete the model
        migrations.DeleteModel(
            name='ScheduledMessage',
        ),
    ]
