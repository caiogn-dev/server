"""
Remove the legacy ConversationHandover model from the conversations app.
Canonical model is in apps.handover.ConversationHandover (table: handover_conversationhandover).
The old table (conversation_handovers) is dropped by this migration.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("conversations", "0004_merge"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ConversationHandover",
        ),
    ]
